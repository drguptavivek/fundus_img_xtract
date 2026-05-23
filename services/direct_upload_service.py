"""Shared service for direct image upload creation."""
from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import BinaryIO

import magic

from auth.utils import utcnow
from models import Area, Camera, DirectImageUpload, DirectImageVerify, GradingTask, Hospital, LabUnit
from upload_profiles.service import UploadProfileError, UploadSelection, validate_direct_upload_scope
from utils.fileUtils import get_upload_dirs
from utils.file_hashing import find_duplicate_file, get_hash_algorithm, hash_file_content
from utils.filename_sanitizer import sanitize_storage_filename
from utils.filename_validation import validate_upload_filename
from utils.utils2 import uniquify


logger = logging.getLogger(__name__)
DEFAULT_DIRECT_ALLOWED_MIMETYPES = {"image/jpeg", "image/png"}
DEFAULT_DIRECT_MAX_FILE_SIZE_BYTES = 15 * 1024 * 1024


@dataclass(frozen=True)
class DirectUploadSelection:
    project_id: int
    lab_unit_id: int
    disease_id: int
    camera_id: int
    area_id: int
    is_mydriatic: bool = False
    profile_id: int | None = None


@dataclass(frozen=True)
class DirectUploadItemResult:
    filename: str
    status: str
    message: str
    upload_id: int | None = None
    image_uuid: str | None = None
    task_id: int | None = None
    task_uuid: str | None = None
    image_url: str | None = None
    thumbnail_url: str | None = None
    duplicate: bool = False


@dataclass(frozen=True)
class DirectUploadBatchResult:
    items: list[DirectUploadItemResult]
    upload_profile: object

    @property
    def uploaded_count(self) -> int:
        return sum(1 for item in self.items if item.status == "success")

    @property
    def duplicate_count(self) -> int:
        return sum(1 for item in self.items if item.status == "duplicate")

    @property
    def accepted_count(self) -> int:
        return self.uploaded_count + self.duplicate_count

    @property
    def success_count(self) -> int:
        return self.accepted_count

    @property
    def error_count(self) -> int:
        return sum(1 for item in self.items if item.status == "error")


def resolve_direct_upload_profile(*, db, user_id: int, selection: DirectUploadSelection):
    """Resolve the selected profile for a direct upload without creating records."""
    return validate_direct_upload_scope(
        db,
        user_id,
        UploadSelection(
            project_id=selection.project_id,
            lab_unit_id=selection.lab_unit_id,
            disease_id=selection.disease_id,
            camera_id=selection.camera_id,
            area_id=selection.area_id,
            is_mydriatic=selection.is_mydriatic,
            profile_id=selection.profile_id,
        ),
    )


def create_direct_upload_batch(
    *,
    db,
    files: list,
    user_id: int,
    selection: DirectUploadSelection,
    allowed_mimetypes: set[str] | None = None,
    max_file_size_bytes: int = DEFAULT_DIRECT_MAX_FILE_SIZE_BYTES,
    request_url_builder=None,
    thumbnail_url_builder=None,
    remarks: str | None = None,
) -> DirectUploadBatchResult:
    """Create unverified direct image uploads after validating the selected upload profile."""
    return _create_direct_upload_batch(
        db=db,
        files=files,
        user_id=user_id,
        selection=selection,
        allowed_mimetypes=allowed_mimetypes,
        max_file_size_bytes=max_file_size_bytes,
        verification_status=None,
        verification_remarks=None,
        verification_user_id=None,
        create_task=False,
        resolved_upload_profile=None,
        request_url_builder=request_url_builder,
        thumbnail_url_builder=thumbnail_url_builder,
        remarks=remarks,
    )


def create_unverified_direct_upload_task_batch(
    *,
    db,
    files: list,
    user_id: int,
    selection: DirectUploadSelection,
    allowed_mimetypes: set[str] | None = None,
    max_file_size_bytes: int = DEFAULT_DIRECT_MAX_FILE_SIZE_BYTES,
    resolved_upload_profile=None,
    verification_remarks: str | None = None,
    verification_user_id: int | None = None,
    request_url_builder=None,
    thumbnail_url_builder=None,
    remarks: str | None = None,
) -> DirectUploadBatchResult:
    """Create unverified direct image uploads and disease tasks for API-triggered AI workflows."""
    return _create_direct_upload_batch(
        db=db,
        files=files,
        user_id=user_id,
        selection=selection,
        allowed_mimetypes=allowed_mimetypes,
        max_file_size_bytes=max_file_size_bytes,
        verification_status="unverified" if verification_remarks else None,
        verification_remarks=verification_remarks,
        verification_user_id=verification_user_id,
        create_task=True,
        resolved_upload_profile=resolved_upload_profile,
        request_url_builder=request_url_builder,
        thumbnail_url_builder=thumbnail_url_builder,
        remarks=remarks,
    )


def _create_direct_upload_batch(
    *,
    db,
    files: list,
    user_id: int,
    selection: DirectUploadSelection,
    allowed_mimetypes: set[str] | None,
    max_file_size_bytes: int,
    verification_status: str | None,
    verification_remarks: str | None,
    verification_user_id: int | None,
    create_task: bool,
    resolved_upload_profile,
    request_url_builder,
    thumbnail_url_builder,
    remarks: str | None,
) -> DirectUploadBatchResult:
    upload_profile = resolved_upload_profile or resolve_direct_upload_profile(db=db, user_id=user_id, selection=selection)
    lab_unit = db.get(LabUnit, upload_profile.lab_unit_id)
    hospital = db.get(Hospital, upload_profile.hospital_id)
    camera = db.get(Camera, selection.camera_id)
    area = db.get(Area, selection.area_id)
    if not all([lab_unit, hospital, camera, area]):
        raise UploadProfileError("Invalid upload selection.", code="invalid_selection")

    allowed_mimetypes = allowed_mimetypes or DEFAULT_DIRECT_ALLOWED_MIMETYPES
    orig_dir, _edited_dir, dup_dir, folder_rel = get_upload_dirs(user_id)
    items = [
        _create_direct_upload_item(
            db=db,
            file=file,
            user_id=user_id,
            upload_profile=upload_profile,
            hospital_id=hospital.id,
            lab_unit_id=lab_unit.id,
            camera_id=camera.id,
            area_id=area.id,
            disease_id=selection.disease_id,
            is_mydriatic=selection.is_mydriatic,
            orig_dir=orig_dir,
            dup_dir=dup_dir,
            folder_rel=folder_rel,
            allowed_mimetypes=allowed_mimetypes,
            max_file_size_bytes=max_file_size_bytes,
            verification_status=verification_status,
            verification_remarks=verification_remarks,
            verification_user_id=verification_user_id,
            create_task=create_task,
            request_url_builder=request_url_builder,
            thumbnail_url_builder=thumbnail_url_builder,
            remarks=remarks,
        )
        for file in files
    ]
    return DirectUploadBatchResult(items=items, upload_profile=upload_profile)


def _create_direct_upload_item(
    *,
    db,
    file,
    user_id: int,
    upload_profile,
    hospital_id: int,
    lab_unit_id: int,
    camera_id: int,
    area_id: int,
    disease_id: int,
    is_mydriatic: bool,
    orig_dir,
    dup_dir,
    folder_rel: str,
    allowed_mimetypes: set[str],
    max_file_size_bytes: int,
    verification_status: str | None,
    verification_remarks: str | None,
    verification_user_id: int | None,
    create_task: bool,
    request_url_builder,
    thumbnail_url_builder,
    remarks: str | None,
) -> DirectUploadItemResult:
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
    duplicate = find_duplicate_file(file_hash, len(content), db)
    if duplicate:
        uniquify(dup_dir, filename).write_bytes(content)
        task = _direct_image_task_for_duplicate(
            db=db,
            upload=duplicate,
            disease_id=disease_id,
            lab_unit_id=lab_unit_id,
            create_task=create_task,
        )
        return DirectUploadItemResult(
            filename=filename,
            status="duplicate",
            message="Duplicate file.",
            upload_id=duplicate.id,
            image_uuid=duplicate.uuid,
            task_id=task.id if task else None,
            task_uuid=task.uuid if task else None,
            image_url=request_url_builder(duplicate.uuid) if request_url_builder else None,
            thumbnail_url=thumbnail_url_builder(duplicate.uuid) if thumbnail_url_builder else None,
            duplicate=True,
        )

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
        project_id=upload_profile.project_id,
        camera_id=camera_id,
        disease_id=disease_id,
        area_id=area_id,
        is_mydriatic=is_mydriatic,
        remarks=remarks,
        thumbnail_filename=None,
        s3_config_id=None,
        s3_object_key=None,
        s3_object_key_thumbnail=None,
    )
    db.add(upload)
    db.flush()

    if verification_status and verification_remarks and verification_user_id:
        db.add(
            DirectImageVerify(
                image_upload_id=upload.id,
                verified_status=verification_status,
                remarks=verification_remarks,
                verified_by_id=verification_user_id,
                verified_at=utcnow(),
            )
        )

    task = None
    if create_task:
        task = (
            db.query(GradingTask)
            .filter(
                GradingTask.direct_image_upload_id == upload.id,
                GradingTask.disease_id == disease_id,
            )
            .one_or_none()
        )
        if task is None:
            task = GradingTask(
                direct_image_upload_id=upload.id,
                disease_id=disease_id,
                lab_unit_id=lab_unit_id,
                state="pending",
            )
            db.add(task)
            db.flush()

    image_url = request_url_builder(upload.uuid) if request_url_builder else None
    thumbnail_url = thumbnail_url_builder(upload.uuid) if thumbnail_url_builder else None
    return DirectUploadItemResult(
        filename=dest.name,
        status="success",
        message="Image uploaded successfully.",
        upload_id=upload.id,
        image_uuid=upload.uuid,
        task_id=task.id if task else None,
        task_uuid=task.uuid if task else None,
        image_url=image_url,
        thumbnail_url=thumbnail_url,
    )


def _direct_image_task_for_duplicate(
    *,
    db,
    upload: DirectImageUpload,
    disease_id: int,
    lab_unit_id: int,
    create_task: bool,
) -> GradingTask | None:
    if not create_task:
        return None
    task = (
        db.query(GradingTask)
        .filter(
            GradingTask.direct_image_upload_id == upload.id,
            GradingTask.disease_id == disease_id,
        )
        .one_or_none()
    )
    if task is not None:
        return task
    task = GradingTask(
        direct_image_upload_id=upload.id,
        disease_id=disease_id,
        lab_unit_id=lab_unit_id,
        state="pending",
    )
    db.add(task)
    db.flush()
    return task


def _read_file_bytes(file: BinaryIO) -> bytes:
    data = file.read()
    try:
        file.seek(0)
    except (AttributeError, OSError, ValueError):
        logger.debug("Uploaded file stream could not be rewound after byte read.", exc_info=True)
    return data


def _error_item(filename: str, message: str) -> DirectUploadItemResult:
    return DirectUploadItemResult(filename=filename, status="error", message=message)
