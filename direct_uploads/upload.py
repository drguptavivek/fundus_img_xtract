# direct_uploads/uploads.py

import os, uuid, hashlib, magic
from pathlib import Path

from utils.file_hashing import hash_file_content, get_hash_algorithm, is_duplicate_file
from datetime import datetime
from utils.filename_sanitizer import sanitize_storage_filename
from flask import request, render_template, redirect, url_for, flash, current_app
from flask_login import current_user
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from utils.utils2 import uniquify
from utils.env_loader import load_environment
from utils.filename_validation import validate_upload_filename, sanitize_filename_for_logging

from . import bp
from db_transaction_manager import get_db_session
from auth.roles import roles_required
from utils.rate_limiter import upload_rate_limit
from models import (
    User, LabUnit, Hospital, DirectImageUpload,
    Camera, Disease, Area, Job, JobItem, AppSetting
)

from utils.fileUtils import get_upload_dirs
from utils.upload_eligibility import get_user_uploadVerify_eligibility, get_user_lab_unit_ids_no_admin_override
from utils.jobUtils import get_recent_zip_uploads
from utils.thumbnail_maintenance_scheduler import queue_missing_thumbnail_regeneration
from utils.log_sanitize import sanitize_log_value


load_environment()


def _to_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _get_int_setting(db_session: Session, key: str, env_var: str, default: int) -> int:
    """
    Resolve integer settings, preferring the database-backed app_settings entry
    and falling back to environment/default values if absent or invalid.
    """
    env_value = _to_int(os.getenv(env_var))
    env_fallback = env_value if env_value is not None else default
    setting = db_session.get(AppSetting, key)
    if setting is None:
        return env_fallback

    value = _to_int(setting.value)
    if value is None:
        current_app.logger.warning(
            "Invalid integer for %s in app_settings (value=%s). Using fallback %s",
            key, setting.value, env_fallback
        )
        return env_fallback

    return value


def _get_csv_setting(db_session: Session, key: str, env_var: str, default: list[str]) -> list[str]:
    """
    Resolve CSV/list settings, preferring the database-backed app_settings entry
    and falling back to environment/default values if absent or invalid.
    """
    def _split_csv(raw: str | None) -> list[str]:
        if not raw:
            return []
        return [part.strip() for part in raw.split(",") if part.strip()]

    env_value = _split_csv(os.getenv(env_var))
    env_fallback = env_value if env_value else default

    setting = db_session.get(AppSetting, key)
    if setting is None:
        return env_fallback

    parsed = _split_csv(setting.value)
    if not parsed:
        current_app.logger.warning(
            "Invalid list/CSV for %s in app_settings (value=%s). Using fallback %s",
            key, setting.value, env_fallback
        )
        return env_fallback

    return parsed


def _get_lifetime_quota(db_session: Session, user) -> int | None:
    """
    Determine the lifetime upload quota for a user.
    Priority:
    1. User-specific file_upload_quota (>0) -> enforce that limit
    2. AppSetting DIRECT_UPLOAD_LIFETIME_QUOTA (fallback env/default)
    3. If resolved quota <=0 or missing -> unlimited (return None)
    """
    user_quota = _to_int(getattr(user, "file_upload_quota", None))
    if user_quota and user_quota > 0:
        return user_quota

    # Resolve default quota
    quota = _get_int_setting(
        db_session,
        "DIRECT_UPLOAD_LIFETIME_QUOTA",
        "DIRECT_UPLOAD_LIFETIME_QUOTA",
        50,
    )
    if quota is not None and quota > 0:
        return quota
    return None  # None means unlimited


@bp.route("/upload", methods=["GET"])
@roles_required("admin", "local_admin", "fileUploader", "optometrist", "data_manager")
def upload_index():
    eligibility = get_user_uploadVerify_eligibility(current_user.id)
    return render_template("direct_uploads/index.html", eligibility=eligibility)


@bp.route("/direct/upload", methods=["GET", "POST"])
@roles_required("admin", "local_admin", "fileUploader", "optometrist", "data_manager")
@upload_rate_limit("60 per minute")  # Reduced to prevent abuse while allowing reasonable uploads
def upload():
    with get_db_session() as db_session:
        allowed_lab_units = get_user_lab_unit_ids_no_admin_override(current_user.id)
        if not allowed_lab_units:
            flash("You are not mapped to any lab units.", "warning")
            return redirect(url_for("home.index"))

        if request.method == "POST":
            # ---- form fields ----
            hospital_id = _to_int(request.form.get("hospital_id"))
            lab_unit_id = _to_int(request.form.get("lab_unit_id"))
            camera_id   = _to_int(request.form.get("camera_id"))
            disease_id  = _to_int(request.form.get("disease_id"))
            area_id     = _to_int(request.form.get("area_id"))
            is_mydriatic = request.form.get("is_mydriatic") == "on"
            files = request.files.getlist("files")

            current_app.logger.info(
                "Direct upload initiated by user %s (ID: %s) from IP %s",
                sanitize_log_value(current_user.username),
                sanitize_log_value(current_user.id),
                sanitize_log_value(request.remote_addr),
            )
            current_app.logger.info(
                "Upload parameters - Hospital:%s LabUnit:%s Camera:%s Disease:%s Area:%s Mydriatic:%s",
                sanitize_log_value(hospital_id),
                sanitize_log_value(lab_unit_id),
                sanitize_log_value(camera_id),
                sanitize_log_value(disease_id),
                sanitize_log_value(area_id),
                sanitize_log_value(is_mydriatic),
            )

            # ---- limits & allowed types ----
            MAX_FILES_ALLOWED = _get_int_setting(
                db_session, "DIRECT_UPLOAD_MAX_FILES", "DIRECT_UPLOAD_MAX_FILES", 100
            )
            MAX_FILE_SIZE_MB = _get_int_setting(
                db_session, "DIRECT_UPLOAD_MAX_FILE_SIZE_MB", "DIRECT_UPLOAD_MAX_FILE_SIZE_MB", 5
            )
            MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
            ALLOWED_MIMETYPES = _get_csv_setting(
                db_session,
                "DIRECT_UPLOAD_ALLOWED_MIMETYPES",
                "DIRECT_UPLOAD_ALLOWED_MIMETYPES",
                ["image/jpeg", "image/png"],
            )

            # ---- validate required fields ----
            if not all([hospital_id, lab_unit_id, camera_id, disease_id, area_id]):
                current_app.logger.warning(
                    "Direct upload failed: missing fields for user %s (%s)",
                    sanitize_log_value(current_user.username),
                    sanitize_log_value(current_user.id),
                )
                flash("All fields are required.", "danger")
                return redirect(url_for("direct_uploads.upload"), code=303)

            hospital = db_session.get(Hospital, hospital_id)
            lab_unit = db_session.get(LabUnit, lab_unit_id)
            camera   = db_session.get(Camera,   camera_id)
            disease  = db_session.get(Disease,  disease_id)
            area     = db_session.get(Area,     area_id)

            if not all([hospital, lab_unit, camera, disease, area]):
                current_app.logger.warning(
                    "Direct upload failed: invalid selection for user %s (%s)",
                    sanitize_log_value(current_user.username),
                    sanitize_log_value(current_user.id),
                )
                flash("Invalid selection for one or more fields.", "danger")
                return redirect(url_for("direct_uploads.upload"), code=303)

            # Optional consistency: lab unit must belong to hospital
            if getattr(lab_unit, "hospital_id", None) != hospital.id:
                flash("Selected Lab Unit does not belong to the selected Hospital.", "danger")
                return redirect(url_for("direct_uploads.upload"), code=303)

            # Enforce user-level lab unit eligibility
            if lab_unit.id not in allowed_lab_units:
                flash("You don't have access to the selected lab unit.", "danger")
                return redirect(url_for("direct_uploads.upload"), code=303)
 
            # ---- job bookkeeping ----
            job_token = str(uuid.uuid4())
            new_job = Job(
                token=job_token,
                status="processing",
                uploader_user_id=current_user.id,
                uploader_username=current_user.username,
                uploader_ip=request.remote_addr,
                lab_unit_id=lab_unit.id,
                upload_type="direct image",
            )
            db_session.add(new_job)
            db_session.flush()
            current_app.logger.info(
                "Created new job %s for user %s (%s)",
                sanitize_log_value(new_job.id),
                sanitize_log_value(current_user.username),
                sanitize_log_value(current_user.id),
            )

            # ---- dirs for this user/day ----
            orig_dir, edited_dir, dup_dir, folder_rel = get_upload_dirs(current_user.id)
    

            # ---- process files ----
            files = files[:MAX_FILES_ALLOWED]  # hard-cap
            if not files:
                flash("No files selected.", "warning")
                return redirect(url_for("direct_uploads.upload"), code=303)

            current_app.logger.info(
                "Processing %s files for upload",
                sanitize_log_value(len(files)),
            )

            tasks_to_enqueue = []
            job_items = []

            for file in files:
                original_filename = file.filename or ""

                # SECURITY: Validate filename before any processing
                # This prevents path traversal, null byte injection, and log injection attacks
                is_valid, validation_error = validate_upload_filename(original_filename)

                if not is_valid:
                    # Log the original filename (sanitized) and the validation error
                    state, detail = "error", f"Invalid filename: {validation_error}"
                    current_app.logger.warning(
                        "File upload rejected - %s. Original filename: %s",
                        validation_error,
                        sanitize_filename_for_logging(original_filename),
                    )
                    job_items.append(JobItem(
                        job_id=new_job.id,
                        filename=sanitize_filename_for_logging(original_filename),
                        state=state,
                        detail=detail,
                        uploader_user_id=current_user.id,
                        uploader_username=current_user.username,
                        uploader_ip=request.remote_addr
                    ))
                    continue

                # Filename is valid, sanitize for storage (ASCII-safe with hash on change)
                try:
                    filename = sanitize_storage_filename(original_filename)
                except ValueError as e:
                    state, detail = "error", f"Invalid filename: {e}"
                    current_app.logger.warning(
                        "File upload error: invalid filename after sanitization (%s)",
                        sanitize_filename_for_logging(original_filename),
                    )
                    job_items.append(JobItem(
                        job_id=new_job.id,
                        filename=sanitize_filename_for_logging(original_filename),
                        state=state,
                        detail=detail,
                        uploader_user_id=current_user.id,
                        uploader_username=current_user.username,
                        uploader_ip=request.remote_addr
                    ))
                    continue
                state, detail = "queued", ""

                if not filename:
                    state, detail = "error", "No selected file"
                    current_app.logger.warning("File upload error: no selected file")
                else:
                    content = file.read()
                    size = len(content)
                    current_app.logger.info(
                        "Processing file: %s (%s bytes)",
                        sanitize_log_value(filename),
                        sanitize_log_value(size),
                    )

                    if size > MAX_FILE_SIZE_BYTES:
                        state, detail = "error", f"File too large (max {MAX_FILE_SIZE_MB}MB)"
                        current_app.logger.warning(
                            "Too large: %s bytes for %s",
                            sanitize_log_value(size),
                            sanitize_log_value(filename),
                        )
                    else:
                        mime_type = magic.from_buffer(content, mime=True)
                        if mime_type not in ALLOWED_MIMETYPES:
                            state, detail = "error", f"Invalid file type: {mime_type}. Only JPG/PNG allowed."
                            current_app.logger.warning(
                                "Invalid type %s for %s",
                                sanitize_log_value(mime_type),
                                sanitize_log_value(filename),
                            )
                        else:
                            # SECURITY: Use SHA-256 instead of MD5 for file hashing (CWE-327)
                            # Truncate to 32 chars due to database column constraint (String(32))
                            # 32 chars of SHA-256 is still cryptographically stronger than MD5
                            full_hash = hash_file_content(content, algorithm=get_hash_algorithm())
                            file_hash = full_hash[:32]  # Truncate to fit existing schema
                            existing = is_duplicate_file(file_hash, len(content), db_session)

                            if existing:
                                # save a copy to dup folder (no DB row)
                                path = uniquify(dup_dir, filename)
                                path.write_bytes(content)
                                state, detail = "error", "Duplicate file"
                                current_app.logger.info(
                                    "Duplicate: %s",
                                    sanitize_log_value(filename),
                                )
                            else:
                                # per-request quota (optional; your config key)
                                lifetime_quota = _get_lifetime_quota(db_session, current_user)
                                upload_count = getattr(current_user, "file_upload_count", 0) or 0
                                if lifetime_quota is not None and upload_count >= lifetime_quota:
                                    state, detail = "error", "Upload quota exceeded"
                                    current_app.logger.warning(
                                        "Quota exceeded for user %s (%s)",
                                        sanitize_log_value(current_user.username),
                                        sanitize_log_value(current_user.id),
                                    )
                                else:
                                    # write original
                                    dest = uniquify(orig_dir, filename)
                                    dest.write_bytes(content)

                                    # create DB row (folder-based; store basenames only)
                                    # Phase 2 Async: Create record immediately, process in background
                                    upload = DirectImageUpload(
                                        original_filename=filename,
                                        filename=dest.name,                 # basename stored
                                        folder_rel=folder_rel,
                                        edited_filename=None,               # not yet
                                        file_hash=file_hash,               # SHA-256 (truncated to 32 chars)
                                        content_hash=file_hash,            # SHA-256 (truncated to 32 chars)
                                        uploader_id=current_user.id,
                                        hospital_id=hospital.id,
                                        lab_unit_id=lab_unit.id,
                                        camera_id=camera.id,
                                        disease_id=disease.id,
                                        area_id=area.id,
                                        is_mydriatic=is_mydriatic,
                                        thumbnail_filename=None,           # Will be generated by async task
                                        s3_config_id=None,                 # Will be handled by S3 sync task (Phase 3)
                                        s3_object_key=None,
                                        s3_object_key_thumbnail=None,
                                    )
                                    db_session.add(upload)
                                    db_session.flush()

                                    # Collect ID for post-commit enqueue
                                    tasks_to_enqueue.append((upload.id, job_token))
                                    current_user.file_upload_count += 1
                                    state, detail = "completed", "File uploaded successfully"
                                    current_app.logger.info(
                                        "Uploaded: %s",
                                        sanitize_log_value(dest.name),
                                    )

                job_items.append(JobItem(
                    job_id=new_job.id,
                    filename=filename,
                    state=state,
                    detail=detail,
                    uploader_user_id=current_user.id,
                    uploader_username=current_user.username,
                    uploader_ip=request.remote_addr
                ))

            db_session.add_all(job_items)
            # Determine job status (Async-aware)
            if any(i.state == "queued" for i in job_items):
                new_job.status = "processing"
            elif all(i.state == "completed" for i in job_items):
                new_job.status = "completed"
            else:
                new_job.status = "done"

            db_session.commit()

            # Enqueue tasks now that DB records are committed
            try:
                from utils.celery_helpers import celery_enabled
                if celery_enabled() and tasks_to_enqueue:
                    from celery import chain
                    from celery_tasks.tasks.direct_upload_tasks import (
                        process_direct_upload_thumbnail_task, 
                        process_direct_data_combined_task
                    )
                    
                    for uid, token in tasks_to_enqueue:
                        chain(
                            process_direct_upload_thumbnail_task.s(uid, token, user_id=current_user.id, hospital_id=hospital.id),
                            process_direct_data_combined_task.s(token)
                        ).apply_async()
            except Exception as e:
                current_app.logger.error("Failed to enqueue direct upload tasks: %s", e)

            ok = sum(1 for i in job_items if i.state in ("completed", "queued"))
            err = len(job_items) - ok
            current_app.logger.info(
                "Job %s accepted. Queued/OK:%s Errors:%s",
                sanitize_log_value(new_job.id),
                sanitize_log_value(ok),
                sanitize_log_value(err),
            )

            # Trigger a background missing-thumbnail regeneration to catch any gaps
            try:
                queue_missing_thumbnail_regeneration(current_app, schedule_time="post_direct_upload", limit=200)
            except Exception as e:
                current_app.logger.warning(
                    "Could not queue thumbnail regeneration after upload: %s",
                    sanitize_log_value(e),
                )

            flash("Upload process initiated. Check status for details.", "info")
            return redirect(url_for("jobs.upload_processing", job_id=new_job.token), code=303)

        # ---------------- GET: build form data ----------------
        current_app.logger.info(
            "Direct upload page accessed by %s (%s)",
            sanitize_log_value(current_user.username),
            sanitize_log_value(current_user.id),
        )

        user = db_session.get(User, current_user.id)  # attaches to session
        user_lab_unit_ids = set(get_user_lab_unit_ids_no_admin_override(current_user.id))

        lab_units = db_session.execute(
            select(LabUnit)
            .where(LabUnit.id.in_(user_lab_unit_ids))
            .options(selectinload(LabUnit.hospital))
            .order_by(LabUnit.id)
        ).scalars().all()

        accessible_hospital_ids = {lu.hospital_id for lu in lab_units}
        hospitals = db_session.execute(
            select(Hospital).where(Hospital.id.in_(accessible_hospital_ids)).order_by(Hospital.name)
        ).scalars().all()

        cameras  = db_session.execute(select(Camera).order_by(Camera.name)).scalars().all()
        diseases = db_session.execute(select(Disease).order_by(Disease.name)).scalars().all()
        areas    = db_session.execute(select(Area).order_by(Area.name)).scalars().all()

        # Get recent direct image uploads for display
        recent_uploads = get_recent_zip_uploads(limit=5, job_type="direct image")

        lifetime_quota = _get_lifetime_quota(db_session, current_user)

        display_max_files = _get_int_setting(
            db_session, "DIRECT_UPLOAD_MAX_FILES", "DIRECT_UPLOAD_MAX_FILES", 100
        )
        display_max_mb = _get_int_setting(
            db_session, "DIRECT_UPLOAD_MAX_FILE_SIZE_MB", "DIRECT_UPLOAD_MAX_FILE_SIZE_MB", 5
        )

        return render_template(
            "direct_uploads/upload.html",
            hospitals=hospitals,
            lab_units=lab_units,
            cameras=cameras,
            diseases=diseases,
            areas=areas,
            recent_uploads=recent_uploads,
            max_files_per_upload=display_max_files,
            per_file_mb_limit=display_max_mb,
            lifetime_quota=lifetime_quota,
        )


# ============================================================================
# S3 Upload Integration (Multi-Tenant Storage)
# ============================================================================

def _upload_to_s3_and_get_metadata(
    hospital_id: int,
    file_content: bytes,
    local_path,
    file_type: str = "original"
) -> dict | None:
    """
    Upload file to S3 and return metadata for database storage.

    Args:
        hospital_id: Hospital ID
        file_content: File content as bytes
        local_path: Local filesystem path for the file
        file_type: Type of file (original, thumbnail, edited_thumbnail)

    Returns:
        Dict with S3 metadata or None if S3 not configured:
        - s3_config_id
        - s3_object_key
        - backend: "s3"
        Returns None if hospital has no S3 config
    """
    try:
        from utils.s3_upload_handler import (
            get_active_s3_config,
            upload_file_to_s3
        )
        from utils.s3_paths import s3_key_from_local_path

        # Check if hospital has active S3 config
        s3_config = get_active_s3_config(hospital_id)
        if not s3_config:
            return None

        # Generate S3 object key based on local path
        object_key = s3_key_from_local_path(local_path)

        # Upload to S3
        upload_file_to_s3(s3_config, file_content, object_key)

        current_app.logger.info(
            "S3 upload successful for hospital_id=%d, file_type=%s, filename=%s, object_key=%s",
            hospital_id,
            file_type,
            sanitize_log_value(Path(local_path).name),
            sanitize_log_value(object_key)
        )

        return {
            "s3_config_id": s3_config.id,
            "s3_object_key": object_key,
            "backend": "s3",
            "provider": s3_config.provider,
        }

    except Exception as e:
        current_app.logger.error(
            "S3 upload failed for hospital_id=%d, filename=%s: %s",
            hospital_id,
            sanitize_log_value(filename),
            sanitize_log_value(e),
        )
        # Check fallback policy before re-raising
        from utils.s3_upload_handler import get_active_s3_config
        s3_config = get_active_s3_config(hospital_id)
        if s3_config and s3_config.fallback_policy == "never":
            # Fail hard - no local fallback
            raise ValueError(f"S3 upload failed and fallback is disabled: {e}")
        return None


def _upload_thumbnail_to_s3(
    hospital_id: int,
    thumbnail_content: bytes,
    thumbnail_path
) -> dict | None:
    """Upload thumbnail to S3. Returns S3 metadata or None."""
    return _upload_to_s3_and_get_metadata(
        hospital_id,
        thumbnail_content,
        thumbnail_path,
        file_type="thumbnail"
    )


def _generate_hmac_media_url(file_uuid: str, hospital_id: int) -> str | None:
    """
    Generate HMAC-signed media URL for a file.

    Returns:
        Media URL with token/expires parameters, or None if S3 not configured
    """
    try:
        from utils.s3_url_signing import generate_media_url
        return generate_media_url(file_uuid, hospital_id, variant="orig")
    except Exception as e:
        current_app.logger.warning(
            "Failed to generate HMAC URL for uuid=%s, hospital_id=%s: %s",
            file_uuid,
            hospital_id,
            e
        )
        return None


def _get_storage_backend_info(hospital_id: int) -> dict:
    """
    Get storage backend information for API responses.

    Returns:
        Dict with backend info
    """
    from utils.s3_upload_handler import get_storage_backend_info
    return get_storage_backend_info(hospital_id)
