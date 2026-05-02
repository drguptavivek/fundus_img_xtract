from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from db_transaction_manager import transaction_scope
from models import AIModelIntegration, Disease
from job_store import db_create_job
from services.direct_upload_service import (
    DirectUploadSelection,
    create_unverified_direct_upload_task_batch,
    resolve_direct_upload_profile,
)
from services.wadhwani_glaucoma_inference import WADHWANI_PROVIDER, WadhwaniInferenceResult
from utils.celery_helpers import enqueue_task
from utils.log_sanitize import sanitize_log_value
from utils.thumbnail_maintenance_scheduler import queue_missing_thumbnail_regeneration
from upload_profiles.service import UPLOAD_KIND_DIRECT_IMAGE, UploadProfileError


MAX_GLAUCOMA_AI_UPLOAD_FILES = 10
DEFAULT_ALLOWED_MIMETYPES = {"image/jpeg", "image/png"}
DEFAULT_MAX_FILE_SIZE_BYTES = 15 * 1024 * 1024
GLAUCOMA_AI_UPLOAD_VERIFICATION_REMARK = "Uploaded for Wadhwani glaucoma AI workflow; human verification pending."
GLAUCOMA_AI_UPLOAD_LEGACY_VERIFICATION_REMARK = "Verified automatically for Wadhwani glaucoma AI upload."
GLAUCOMA_AI_UPLOAD_MARKER_REMARKS = (
    GLAUCOMA_AI_UPLOAD_VERIFICATION_REMARK,
    GLAUCOMA_AI_UPLOAD_LEGACY_VERIFICATION_REMARK,
)


@dataclass(frozen=True)
class GlaucomaAIUploadSelection:
    project_id: int
    lab_unit_id: int
    camera_id: int
    area_id: int
    is_mydriatic: bool = False
    profile_id: int | None = None


@dataclass(frozen=True)
class GlaucomaAIUploadItem:
    filename: str
    status: str
    message: str
    upload_id: int | None = None
    image_uuid: str | None = None
    task_id: int | None = None
    task_uuid: str | None = None
    image_url: str | None = None
    thumbnail_url: str | None = None
    inference: WadhwaniInferenceResult | None = None
    job_token: str | None = None


@dataclass(frozen=True)
class GlaucomaAIUploadResult:
    items: list[GlaucomaAIUploadItem]

    @property
    def success_count(self) -> int:
        return sum(1 for item in self.items if item.status in {"success", "queued"})

    @property
    def error_count(self) -> int:
        return sum(1 for item in self.items if item.status not in {"success", "queued"})


def get_glaucoma_disease_id(db) -> int:
    disease = (
        db.query(Disease)
        .filter(Disease.name.ilike("glaucoma"))
        .order_by(Disease.id.asc())
        .first()
    )
    if disease is None:
        raise UploadProfileError("Glaucoma disease is not configured.", code="glaucoma_not_configured")
    return disease.id


def process_glaucoma_ai_uploads(
    *,
    files: list,
    user_id: int,
    username: str,
    remote_addr: str | None,
    selection: GlaucomaAIUploadSelection,
    allowed_mimetypes: set[str] | None = None,
    max_file_size_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES,
    request_url_builder=None,
    thumbnail_url_builder=None,
    app=None,
) -> GlaucomaAIUploadResult:
    allowed_mimetypes = allowed_mimetypes or DEFAULT_ALLOWED_MIMETYPES
    files = [file for file in files if getattr(file, "filename", "")]
    if not files:
        return GlaucomaAIUploadResult([_error_item("", "No files selected.")])
    if len(files) > MAX_GLAUCOMA_AI_UPLOAD_FILES:
        return GlaucomaAIUploadResult(
            [_error_item("", f"Upload at most {MAX_GLAUCOMA_AI_UPLOAD_FILES} images per request.")]
        )

    with transaction_scope() as db:
        glaucoma_disease_id = get_glaucoma_disease_id(db)
        if selection.profile_id is None:
            raise UploadProfileError("Select an upload profile for glaucoma AI upload.", code="profile_required")
        direct_selection = DirectUploadSelection(
            project_id=selection.project_id,
            lab_unit_id=selection.lab_unit_id,
            disease_id=glaucoma_disease_id,
            camera_id=selection.camera_id,
            area_id=selection.area_id,
            is_mydriatic=selection.is_mydriatic,
            profile_id=selection.profile_id,
        )
        upload_profile = resolve_direct_upload_profile(db=db, user_id=user_id, selection=direct_selection)
        _validate_glaucoma_ai_workflow(db, upload_profile, glaucoma_disease_id)
        upload_batch = create_unverified_direct_upload_task_batch(
            db=db,
            files=files,
            user_id=user_id,
            selection=direct_selection,
            allowed_mimetypes=allowed_mimetypes,
            max_file_size_bytes=max_file_size_bytes,
            verification_remarks=GLAUCOMA_AI_UPLOAD_VERIFICATION_REMARK,
            verification_user_id=user_id,
            resolved_upload_profile=upload_profile,
            request_url_builder=request_url_builder,
            thumbnail_url_builder=thumbnail_url_builder,
        )
        created_items = [_glaucoma_item_from_direct(item) for item in upload_batch.items]

    queued_items = _enqueue_wadhwani_inference(
        created_items,
        user_id=user_id,
        username=username,
        remote_addr=remote_addr,
        lab_unit_id=selection.lab_unit_id,
        project_id=selection.project_id,
    )

    if app is not None and any(item.upload_id for item in queued_items):
        try:
            queue_missing_thumbnail_regeneration(app, schedule_time="post_glaucoma_ai_upload", limit=50)
        except Exception as exc:  # pragma: no cover - best-effort background maintenance
            app.logger.warning("Could not queue glaucoma AI thumbnail regeneration: %s", sanitize_log_value(exc))

    return GlaucomaAIUploadResult(queued_items)


def _validate_glaucoma_ai_workflow(db, upload_profile, glaucoma_disease_id: int) -> int:
    """Return the linked Wadhwani AI model ID allowed by the selected upload profile."""
    workflow_model_ids = {
        int(workflow["ai_model_id"])
        for workflow in upload_profile.ai_workflows
        if workflow.get("disease_id") == glaucoma_disease_id
        and workflow.get("upload_kind") == UPLOAD_KIND_DIRECT_IMAGE
        and workflow.get("active", True)
    }
    if not workflow_model_ids:
        raise UploadProfileError(
            "Selected upload profile does not enable glaucoma AI inference workflow.",
            code="ai_workflow_not_allowed",
        )

    linked_model_id = db.execute(
        select(AIModelIntegration.ai_model_id)
        .where(AIModelIntegration.provider == WADHWANI_PROVIDER)
        .where(AIModelIntegration.is_enabled.is_(True))
        .where(AIModelIntegration.ai_model_id.in_(workflow_model_ids))
        .order_by(AIModelIntegration.updated_at.desc(), AIModelIntegration.id.desc())
    ).scalars().first()
    if linked_model_id is None:
        raise UploadProfileError(
            "Selected upload profile is not linked to the enabled Wadhwani glaucoma AI model.",
            code="ai_workflow_not_linked",
        )
    return linked_model_id


def _enqueue_wadhwani_inference(
    items: list[GlaucomaAIUploadItem],
    *,
    user_id: int,
    username: str,
    remote_addr: str | None,
    lab_unit_id: int,
    project_id: int,
) -> list[GlaucomaAIUploadItem]:
    task_ids = [item.task_id for item in items if item.status == "success" and item.task_id is not None]
    if not task_ids:
        return items

    job_token = db_create_job(
        [f"task:{task_id}" for task_id in task_ids],
        [],
        uploader_user_id=user_id,
        uploader_username=username,
        uploader_ip=remote_addr,
        lab_unit_id=lab_unit_id,
        project_id=project_id,
        upload_type="glaucoma_ai_upload_inference",
    )
    try:
        enqueue_task(
            "celery_tasks.tasks.wadhwani_tasks.run_wadhwani_glaucoma_batch_task",
            job_token,
            task_ids,
            user_id=user_id,
        )
    except Exception as exc:
        return [
            _replace_item(
                item,
                status="enqueue_failed",
                message=f"Image uploaded, but inference could not be queued: {exc}",
                job_token=job_token,
            )
            if item.task_id in task_ids
            else item
            for item in items
        ]

    return [
        _replace_item(
            item,
            status="queued",
            message="Image uploaded and Wadhwani glaucoma inference queued.",
            job_token=job_token,
        )
        if item.task_id in task_ids
        else item
        for item in items
    ]


def _glaucoma_item_from_direct(item) -> GlaucomaAIUploadItem:
    return GlaucomaAIUploadItem(
        filename=item.filename,
        status=item.status,
        message="Image uploaded and glaucoma task created." if item.status == "success" else item.message,
        upload_id=item.upload_id,
        image_uuid=item.image_uuid,
        task_id=item.task_id,
        task_uuid=item.task_uuid,
        image_url=item.image_url,
        thumbnail_url=item.thumbnail_url,
    )


def _error_item(filename: str, message: str) -> GlaucomaAIUploadItem:
    return GlaucomaAIUploadItem(filename=filename, status="error", message=message)


def _replace_item(
    item: GlaucomaAIUploadItem,
    *,
    status: str,
    message: str,
    job_token: str | None,
) -> GlaucomaAIUploadItem:
    return GlaucomaAIUploadItem(
        filename=item.filename,
        status=status,
        message=message,
        upload_id=item.upload_id,
        image_uuid=item.image_uuid,
        task_id=item.task_id,
        task_uuid=item.task_uuid,
        image_url=item.image_url,
        thumbnail_url=item.thumbnail_url,
        inference=item.inference,
        job_token=job_token,
    )
