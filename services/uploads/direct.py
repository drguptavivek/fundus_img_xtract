"""Direct image upload orchestration shared by web and mobile clients."""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from auth.utils import utcnow
from models import AIModelIntegration, AppSetting, Area, Camera, Disease, Hospital, Job, JobItem, LabUnit, User
from services.direct_upload_service import (
    DEFAULT_DIRECT_MAX_FILE_SIZE_BYTES,
    DirectUploadSelection,
    create_direct_upload_batch,
    create_unverified_direct_upload_task_batch,
    resolve_direct_upload_profile,
)
from services.wadhwani_glaucoma_inference import WADHWANI_PROVIDER
from upload_profiles.service import UPLOAD_KIND_DIRECT_IMAGE, get_user_upload_options_for_kind, validate_profile_upload_scope
from utils.jobUtils import get_recent_zip_uploads
from utils.log_sanitize import sanitize_log_value
from utils.thumbnail_maintenance_scheduler import queue_missing_thumbnail_regeneration
from utils.upload_eligibility import get_user_lab_unit_ids_no_admin_override


@dataclass(frozen=True)
class DirectUploadActor:
    user_id: int
    username: str | None = None
    remote_addr: str | None = None


@dataclass(frozen=True)
class DirectUploadJobRequest:
    profile_id: int | None
    project_id: int
    lab_unit_id: int
    disease_id: int
    camera_id: int
    area_id: int
    is_mydriatic: bool | None = None
    remarks: str | None = None
    idempotency_key: str | None = None
    verification_remarks: str | None = None
    verification_user_id: int | None = None


@dataclass(frozen=True)
class DirectUploadJobResult:
    job: Job
    accepted_count: int
    rejected_count: int
    inference_available: bool
    upload_ids_for_post_commit: tuple[int, ...] = ()
    hospital_id_for_post_commit: int | None = None
    inference_task_ids_for_post_commit: tuple[int, ...] = ()


@dataclass(frozen=True)
class DirectUploadSettings:
    max_files: int
    max_file_size_mb: int
    allowed_mimetypes: tuple[str, ...]
    lifetime_quota: int | None

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024


def create_direct_upload_job(
    *,
    db,
    actor: DirectUploadActor,
    request: DirectUploadJobRequest,
    files: list,
    upload_type: str = "direct image",
    allowed_mimetypes: set[str] | None = None,
    max_file_size_bytes: int = DEFAULT_DIRECT_MAX_FILE_SIZE_BYTES,
    request_url_builder=None,
    thumbnail_url_builder=None,
) -> DirectUploadJobResult:
    """Create direct image uploads and their job bookkeeping in one transaction."""
    if not files:
        raise DirectUploadJobError("At least one file is required.", code="files_required")

    selection = DirectUploadSelection(
        project_id=request.project_id,
        lab_unit_id=request.lab_unit_id,
        disease_id=request.disease_id,
        camera_id=request.camera_id,
        area_id=request.area_id,
        is_mydriatic=request.is_mydriatic if request.is_mydriatic is not None else False,
        profile_id=request.profile_id,
    )
    if request.profile_id:
        profile = validate_profile_upload_scope(
            db,
            actor.user_id,
            profile_id=request.profile_id,
            upload_kind=UPLOAD_KIND_DIRECT_IMAGE,
            disease_id=request.disease_id,
            camera_id=request.camera_id,
            area_id=request.area_id,
            is_mydriatic=request.is_mydriatic,
        )
    else:
        profile = resolve_direct_upload_profile(db=db, user_id=actor.user_id, selection=selection)
    if profile.project_id != request.project_id or profile.lab_unit_id != request.lab_unit_id:
        raise DirectUploadJobError("Selected profile does not match project or lab unit.", code="profile_scope_mismatch", status_code=403)

    is_mydriatic = request.is_mydriatic
    if is_mydriatic is None:
        is_mydriatic = profile.default_is_mydriatic

    executable_workflow = profile_has_executable_direct_workflow(db, profile, disease_id=request.disease_id)
    selection = DirectUploadSelection(
        project_id=request.project_id,
        lab_unit_id=request.lab_unit_id,
        disease_id=request.disease_id,
        camera_id=request.camera_id,
        area_id=request.area_id,
        is_mydriatic=is_mydriatic,
        profile_id=profile.profile_id,
    )
    if executable_workflow:
        batch = create_unverified_direct_upload_task_batch(
            db=db,
            files=files,
            user_id=actor.user_id,
            selection=selection,
            allowed_mimetypes=allowed_mimetypes,
            max_file_size_bytes=max_file_size_bytes,
            resolved_upload_profile=profile,
            request_url_builder=request_url_builder,
            thumbnail_url_builder=thumbnail_url_builder,
            verification_remarks=request.verification_remarks,
            verification_user_id=request.verification_user_id,
            remarks=request.remarks,
        )
    else:
        batch = create_direct_upload_batch(
            db=db,
            files=files,
            user_id=actor.user_id,
            selection=selection,
            allowed_mimetypes=allowed_mimetypes,
            max_file_size_bytes=max_file_size_bytes,
            request_url_builder=request_url_builder,
            thumbnail_url_builder=thumbnail_url_builder,
            remarks=request.remarks,
        )

    job = Job(
        token=str(uuid.uuid4()),
        status=_job_status(batch.success_count, batch.error_count),
        upload_type=upload_type,
        upload_kind=UPLOAD_KIND_DIRECT_IMAGE,
        upload_profile_id=profile.profile_id,
        uploader_user_id=actor.user_id,
        uploader_username=actor.username,
        uploader_ip=actor.remote_addr,
        lab_unit_id=request.lab_unit_id,
        project_id=request.project_id,
        idempotency_key=request.idempotency_key,
    )
    db.add(job)
    db.flush()

    for item in batch.items:
        db.add(
            JobItem(
                job_id=job.id,
                filename=item.filename,
                state="completed"
                if item.status == "success"
                else "duplicate"
                if item.status == "duplicate"
                else "error",
                detail=item.message,
                uploader_user_id=actor.user_id,
                uploader_username=actor.username,
                uploader_ip=actor.remote_addr,
                source_type="direct_image" if item.upload_id else None,
                source_id=item.upload_id,
                source_uuid=item.image_uuid,
                task_id=item.task_id,
                finished_at=utcnow(),
            )
        )
    db.flush()

    return DirectUploadJobResult(
        job=job,
        accepted_count=batch.success_count,
        rejected_count=batch.error_count,
    inference_available=executable_workflow and any(item.task_id for item in batch.items),
    upload_ids_for_post_commit=tuple(item.upload_id for item in batch.items if item.upload_id),
    inference_task_ids_for_post_commit=tuple(
        item.task_id for item in batch.items if executable_workflow and item.task_id
    ),
    )


def create_web_direct_upload_from_form(*, db, user_id: int, username: str | None, remote_addr: str | None, form, files) -> DirectUploadJobResult:
    """Validate a web direct-upload form and create the upload job."""
    hospital_id = _required_int(form, "hospital_id")
    project_id = _required_int(form, "project_id")
    lab_unit_id = _required_int(form, "lab_unit_id")
    camera_id = _required_int(form, "camera_id")
    disease_id = _required_int(form, "disease_id")
    area_id = _required_int(form, "area_id")
    is_mydriatic = form.get("is_mydriatic") == "on"

    allowed_lab_units = set(get_user_lab_unit_ids_no_admin_override(user_id))
    if not allowed_lab_units:
        raise DirectUploadJobError("You are not mapped to any lab units.", code="lab_unit_required", status_code=403)

    lab_unit = db.get(LabUnit, lab_unit_id)
    if lab_unit is None:
        raise DirectUploadJobError("Invalid selection for one or more fields.", code="invalid_selection")
    if lab_unit.hospital_id != hospital_id:
        raise DirectUploadJobError("Selected Lab Unit does not belong to the selected Hospital.", code="lab_unit_hospital_mismatch")
    if lab_unit.id not in allowed_lab_units:
        raise DirectUploadJobError("You don't have access to the selected lab unit.", code="lab_unit_forbidden", status_code=403)

    user = db.get(User, user_id)
    if user is None:
        raise DirectUploadJobError("Invalid upload user.", code="invalid_user", status_code=403)

    settings = get_direct_upload_settings(db, user=user)
    upload_files = list(files.getlist("files"))[: settings.max_files]
    if not upload_files:
        raise DirectUploadJobError("No files selected.", code="files_required")
    upload_count = getattr(user, "file_upload_count", 0) or 0
    if settings.lifetime_quota is not None and upload_count >= settings.lifetime_quota:
        raise DirectUploadJobError("Upload quota exceeded.", code="upload_quota_exceeded", status_code=403)

    result = create_direct_upload_job(
        db=db,
        actor=DirectUploadActor(user_id=user_id, username=username, remote_addr=remote_addr),
        request=DirectUploadJobRequest(
            profile_id=_optional_int(form, "profile_id"),
            project_id=project_id,
            lab_unit_id=lab_unit.id,
            disease_id=disease_id,
            camera_id=camera_id,
            area_id=area_id,
            is_mydriatic=is_mydriatic,
            remarks=(form.get("remarks") or "").strip() or None,
        ),
        files=upload_files,
        upload_type="direct image",
        allowed_mimetypes=set(settings.allowed_mimetypes),
        max_file_size_bytes=settings.max_file_size_bytes,
    )
    if user.file_upload_count is None:
        user.file_upload_count = 0
    user.file_upload_count += result.accepted_count
    return DirectUploadJobResult(
        job=result.job,
        accepted_count=result.accepted_count,
        rejected_count=result.rejected_count,
        inference_available=result.inference_available,
        upload_ids_for_post_commit=result.upload_ids_for_post_commit,
        hospital_id_for_post_commit=lab_unit.hospital_id,
        inference_task_ids_for_post_commit=result.inference_task_ids_for_post_commit,
    )


def build_web_direct_upload_context(*, db, user_id: int) -> dict[str, Any]:
    """Build template context for the legacy web direct-upload page."""
    user_lab_unit_ids = set(get_user_lab_unit_ids_no_admin_override(user_id))
    lab_units = db.execute(
        select(LabUnit)
        .where(LabUnit.id.in_(user_lab_unit_ids))
        .options(selectinload(LabUnit.hospital))
        .order_by(LabUnit.id)
    ).scalars().all()
    accessible_hospital_ids = {lab_unit.hospital_id for lab_unit in lab_units}
    hospitals = db.execute(select(Hospital).where(Hospital.id.in_(accessible_hospital_ids)).order_by(Hospital.name)).scalars().all()
    cameras = db.execute(select(Camera).order_by(Camera.name)).scalars().all()
    diseases = db.execute(select(Disease).order_by(Disease.name)).scalars().all()
    areas = db.execute(select(Area).order_by(Area.name)).scalars().all()
    upload_options = get_user_upload_options_for_kind(db, user_id, UPLOAD_KIND_DIRECT_IMAGE)
    settings = get_direct_upload_settings(db, user=db.get(User, user_id))
    return {
        "hospitals": [{"id": hospital.id, "name": hospital.name} for hospital in hospitals],
        "lab_units": [{"id": lab_unit.id, "name": lab_unit.name, "hospital_id": lab_unit.hospital_id} for lab_unit in lab_units],
        "cameras": [{"id": camera.id, "name": camera.name} for camera in cameras],
        "diseases": [{"id": disease.id, "name": disease.name} for disease in diseases],
        "areas": [{"id": area.id, "name": area.name} for area in areas],
        "projects": upload_options.projects,
        "upload_profiles": upload_options.profiles,
        "recent_uploads": get_recent_zip_uploads(limit=5, job_type="direct image", uploader_user_id=user_id),
        "max_files_per_upload": settings.max_files,
        "per_file_mb_limit": settings.max_file_size_mb,
        "lifetime_quota": settings.lifetime_quota,
    }


def get_direct_upload_settings(db, *, user=None) -> DirectUploadSettings:
    return DirectUploadSettings(
        max_files=_get_int_setting(db, "DIRECT_UPLOAD_MAX_FILES", "DIRECT_UPLOAD_MAX_FILES", 100),
        max_file_size_mb=_get_int_setting(db, "DIRECT_UPLOAD_MAX_FILE_SIZE_MB", "DIRECT_UPLOAD_MAX_FILE_SIZE_MB", 15),
        allowed_mimetypes=tuple(
            _get_csv_setting(
                db,
                "DIRECT_UPLOAD_ALLOWED_MIMETYPES",
                "DIRECT_UPLOAD_ALLOWED_MIMETYPES",
                ["image/jpeg", "image/png"],
            )
        ),
        lifetime_quota=_get_lifetime_quota(db, user),
    )


def enqueue_direct_upload_post_commit(app, *, user_id: int, upload_ids: tuple[int, ...], job_token: str, hospital_id: int | None) -> None:
    """Schedule background work that must run after the upload transaction commits."""
    try:
        from utils.celery_helpers import celery_enabled

        if celery_enabled() and upload_ids:
            from celery import chain
            from celery_tasks.tasks.direct_upload_tasks import (
                process_direct_data_combined_task,
                process_direct_upload_thumbnail_task,
            )

            for upload_id in upload_ids:
                chain(
                    process_direct_upload_thumbnail_task.s(upload_id, job_token, user_id=user_id, hospital_id=hospital_id),
                    process_direct_data_combined_task.s(job_token),
                ).apply_async()
    except Exception as exc:
        app.logger.error("Failed to enqueue direct upload tasks: %s", sanitize_log_value(exc))

    try:
        queue_missing_thumbnail_regeneration(app, schedule_time="post_direct_upload", limit=200)
    except Exception as exc:
        app.logger.warning("Could not queue thumbnail regeneration after upload: %s", sanitize_log_value(exc))


def direct_upload_response_payload(result: DirectUploadJobResult) -> dict[str, Any]:
    return {
        "upload_token": result.job.token,
        "upload_kind": UPLOAD_KIND_DIRECT_IMAGE,
        "profile_id": result.job.upload_profile_id,
        "status": result.job.status,
        "accepted_count": result.accepted_count,
        "rejected_count": result.rejected_count,
        "inference_available": result.inference_available,
    }


def profile_has_executable_direct_workflow(db, profile, *, disease_id: int) -> bool:
    executable_model_ids = _executable_ai_model_ids(db)
    return any(
        workflow.get("active", True)
        and workflow.get("upload_kind") == UPLOAD_KIND_DIRECT_IMAGE
        and workflow.get("disease_id") == disease_id
        and int(workflow.get("ai_model_id") or 0) in executable_model_ids
        for workflow in profile.ai_workflows
    )


class DirectUploadJobError(ValueError):
    def __init__(self, message: str, *, code: str = "invalid_direct_upload", status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


def _job_status(success_count: int, error_count: int) -> str:
    if success_count == 0:
        return "error"
    if error_count:
        return "partial_error"
    return "completed"


def _required_int(form, name: str) -> int:
    value = _optional_int(form, name)
    if value is None or value <= 0:
        raise DirectUploadJobError(f"{name} is required.", code=f"{name}_required")
    return value


def _optional_int(form, name: str) -> int | None:
    try:
        return int(form.get(name))
    except (TypeError, ValueError):
        return None


def _get_int_setting(db, key: str, env_var: str, default: int) -> int:
    env_raw = os.getenv(env_var)
    try:
        env_fallback = int(env_raw) if env_raw is not None else default
    except (TypeError, ValueError):
        env_fallback = default
    setting = db.get(AppSetting, key)
    if setting is None:
        return env_fallback
    try:
        return int(setting.value)
    except (TypeError, ValueError):
        return env_fallback


def _get_csv_setting(db, key: str, env_var: str, default: list[str]) -> list[str]:
    def split_csv(raw: str | None) -> list[str]:
        if not raw:
            return []
        return [part.strip() for part in raw.split(",") if part.strip()]

    env_value = split_csv(os.getenv(env_var))
    env_fallback = env_value if env_value else default
    setting = db.get(AppSetting, key)
    if setting is None:
        return env_fallback
    parsed = split_csv(setting.value)
    return parsed or env_fallback


def _get_lifetime_quota(db, user) -> int | None:
    user_quota = getattr(user, "file_upload_quota", None) if user is not None else None
    try:
        user_quota = int(user_quota) if user_quota is not None else None
    except (TypeError, ValueError):
        user_quota = None
    if user_quota and user_quota > 0:
        return user_quota
    quota = _get_int_setting(db, "DIRECT_UPLOAD_LIFETIME_QUOTA", "DIRECT_UPLOAD_LIFETIME_QUOTA", 50)
    return quota if quota and quota > 0 else None


def _executable_ai_model_ids(db) -> set[int]:
    return {
        int(model_id)
        for model_id in db.execute(
            select(AIModelIntegration.ai_model_id)
            .where(AIModelIntegration.provider == WADHWANI_PROVIDER)
            .where(AIModelIntegration.is_enabled.is_(True))
        ).scalars()
    }
