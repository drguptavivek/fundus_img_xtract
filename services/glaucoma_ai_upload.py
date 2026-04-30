from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

import magic

from auth.utils import utcnow
from db_transaction_manager import transaction_scope
from models import Area, Camera, DirectImageUpload, DirectImageVerify, Disease, GradingTask, Hospital, LabUnit
from job_store import db_create_job
from services.wadhwani_glaucoma_inference import WadhwaniInferenceResult
from utils.celery_helpers import enqueue_task
from utils.fileUtils import get_upload_dirs
from utils.file_hashing import get_hash_algorithm, hash_file_content, is_duplicate_file
from utils.filename_sanitizer import sanitize_storage_filename
from utils.filename_validation import validate_upload_filename
from utils.log_sanitize import sanitize_log_value
from utils.thumbnail_maintenance_scheduler import queue_missing_thumbnail_regeneration
from utils.upload_scope import UploadScopeError, UploadScopeSelection, validate_direct_upload_scope
from utils.utils2 import uniquify


MAX_GLAUCOMA_AI_UPLOAD_FILES = 10
DEFAULT_ALLOWED_MIMETYPES = {"image/jpeg", "image/png"}
DEFAULT_MAX_FILE_SIZE_BYTES = 15 * 1024 * 1024
GLAUCOMA_AI_UPLOAD_VERIFICATION_REMARK = "Verified automatically for Wadhwani glaucoma AI upload."


@dataclass(frozen=True)
class GlaucomaAIUploadSelection:
    project_id: int
    lab_unit_id: int
    camera_id: int
    area_id: int
    is_mydriatic: bool = False


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
        raise UploadScopeError("Glaucoma disease is not configured.", code="glaucoma_not_configured")
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
        upload_mapping = validate_direct_upload_scope(
            db,
            user_id,
            UploadScopeSelection(
                project_id=selection.project_id,
                lab_unit_id=selection.lab_unit_id,
                disease_id=glaucoma_disease_id,
                camera_id=selection.camera_id,
                area_id=selection.area_id,
                is_mydriatic=selection.is_mydriatic,
            ),
        )
        lab_unit = db.get(LabUnit, upload_mapping.lab_unit_id)
        hospital = db.get(Hospital, upload_mapping.hospital_id)
        camera = db.get(Camera, selection.camera_id)
        area = db.get(Area, selection.area_id)
        if not all([lab_unit, hospital, camera, area]):
            raise UploadScopeError("Invalid upload selection.", code="invalid_selection")

        orig_dir, _edited_dir, dup_dir, folder_rel = get_upload_dirs(user_id)
        created_items: list[GlaucomaAIUploadItem] = []

        for file in files:
            item = _create_upload_and_task(
                db=db,
                file=file,
                user_id=user_id,
                username=username,
                remote_addr=remote_addr,
                upload_mapping=upload_mapping,
                hospital_id=hospital.id,
                lab_unit_id=lab_unit.id,
                camera_id=camera.id,
                area_id=area.id,
                glaucoma_disease_id=glaucoma_disease_id,
                is_mydriatic=selection.is_mydriatic,
                orig_dir=orig_dir,
                dup_dir=dup_dir,
                folder_rel=folder_rel,
                allowed_mimetypes=allowed_mimetypes,
                max_file_size_bytes=max_file_size_bytes,
                request_url_builder=request_url_builder,
                thumbnail_url_builder=thumbnail_url_builder,
            )
            created_items.append(item)

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


def _create_upload_and_task(
    *,
    db,
    file,
    user_id: int,
    username: str,
    remote_addr: str | None,
    upload_mapping,
    hospital_id: int,
    lab_unit_id: int,
    camera_id: int,
    area_id: int,
    glaucoma_disease_id: int,
    is_mydriatic: bool,
    orig_dir: Path,
    dup_dir: Path,
    folder_rel: str,
    allowed_mimetypes: set[str],
    max_file_size_bytes: int,
    request_url_builder,
    thumbnail_url_builder,
) -> GlaucomaAIUploadItem:
    original_filename = file.filename or ""
    valid, validation_error = validate_upload_filename(original_filename)
    if not valid:
        return _error_item(original_filename, f"Invalid filename: {validation_error}")

    try:
        filename = sanitize_storage_filename(original_filename)
    except ValueError as exc:
        return _error_item(original_filename, f"Invalid filename: {exc}")

    content = _read_file_bytes(file)
    if not content:
        return _error_item(filename, "Empty file.")
    if len(content) > max_file_size_bytes:
        max_mb = max_file_size_bytes // (1024 * 1024)
        return _error_item(filename, f"File too large (max {max_mb}MB).")

    mime_type = magic.from_buffer(content, mime=True)
    if mime_type not in allowed_mimetypes:
        return _error_item(filename, f"Invalid file type: {mime_type}. Only JPG/PNG allowed.")

    full_hash = hash_file_content(content, algorithm=get_hash_algorithm())
    file_hash = full_hash[:32]
    duplicate = is_duplicate_file(file_hash, len(content), db)
    if duplicate:
        uniquify(dup_dir, filename).write_bytes(content)
        return _error_item(filename, "Duplicate file.")

    dest = uniquify(orig_dir, filename)
    dest.write_bytes(content)

    upload = DirectImageUpload(
        original_filename=filename,
        filename=dest.name,
        edited_filename=None,
        folder_rel=folder_rel,
        file_hash=file_hash,
        content_hash=file_hash,
        uploader_id=user_id,
        hospital_id=hospital_id,
        lab_unit_id=lab_unit_id,
        project_id=upload_mapping.project_id,
        camera_id=camera_id,
        disease_id=glaucoma_disease_id,
        area_id=area_id,
        is_mydriatic=is_mydriatic,
        thumbnail_filename=None,
        s3_config_id=None,
        s3_object_key=None,
        s3_object_key_thumbnail=None,
    )
    db.add(upload)
    db.flush()

    db.add(
        DirectImageVerify(
            image_upload_id=upload.id,
            verified_status="verified",
            remarks=GLAUCOMA_AI_UPLOAD_VERIFICATION_REMARK,
            verified_by_id=user_id,
            verified_at=utcnow(),
        )
    )

    task = (
        db.query(GradingTask)
        .filter(
            GradingTask.direct_image_upload_id == upload.id,
            GradingTask.disease_id == glaucoma_disease_id,
        )
        .one_or_none()
    )
    if task is None:
        task = GradingTask(
            direct_image_upload_id=upload.id,
            disease_id=glaucoma_disease_id,
            lab_unit_id=lab_unit_id,
            state="pending",
        )
        db.add(task)
        db.flush()

    image_url = request_url_builder(upload.uuid) if request_url_builder else None
    thumbnail_url = thumbnail_url_builder(upload.uuid) if thumbnail_url_builder else None
    return GlaucomaAIUploadItem(
        filename=dest.name,
        status="success",
        message="Image uploaded and glaucoma task created.",
        upload_id=upload.id,
        image_uuid=upload.uuid,
        task_id=task.id,
        task_uuid=task.uuid,
        image_url=image_url,
        thumbnail_url=thumbnail_url,
    )


def _read_file_bytes(file: BinaryIO) -> bytes:
    data = file.read()
    try:
        file.seek(0)
    except Exception:
        pass
    return data


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
