# uploads/routes.py
import os
from pathlib import Path
from datetime import datetime, timezone
from flask import (
    render_template, request, redirect, url_for, flash, current_app
)
from flask_login import current_user
from werkzeug.utils import secure_filename
from sqlalchemy.orm import selectinload
from models import Hospital, LabUnit, UPLOAD_DIR, AppSetting, Camera
import json
from job_store import db_create_job
from worker import queue_job
from . import bp
from auth.roles import roles_required
from utils.upload_eligibility import get_user_lab_unit_ids_no_admin_override
from upload_profiles.service import (
    UPLOAD_KIND_REMIDIO,
    UploadProfileError,
    get_user_upload_options_for_kind,
    validate_remedio_upload_scope,
)
from utils.jobUtils import get_recent_zip_uploads
from db_transaction_manager import get_db_session


ALLOWED_EXT = {"zip"}


def _to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _get_int_setting(db_session, key: str, env_var: str, default: int, *, min_value: int | None = None) -> int:
    """
    Resolve integer settings for ZIP uploads, preferring database values with env/default fallback.
    """
    env_value = _to_int(os.getenv(env_var))
    fallback = env_value if env_value is not None else default

    setting = db_session.get(AppSetting, key)
    if setting is None:
        return fallback

    value = _to_int(setting.value)
    if value is None or (min_value is not None and value < min_value):
        current_app.logger.warning(
            "Invalid integer for %s in app_settings (value=%s). Using fallback %s",
            key, setting.value, fallback
        )
        return fallback

    return value


def _allowed_zip(name: str) -> bool:
    return "." in name and name.rsplit(".", 1)[1].lower() in ALLOWED_EXT

def _uniquify(dest_dir: Path, filename: str) -> Path:
    candidate = dest_dir / secure_filename(filename)
    if not candidate.exists():
        return candidate
    stem, ext = candidate.stem, candidate.suffix
    i = 1
    while True:
        newp = dest_dir / f"{stem} ({i}){ext}"
        if not newp.exists():
            return newp
        i += 1

def _file_size_bytes(file_storage) -> int:
    # Prefer reported content_length when available
    try:
        cl = getattr(file_storage, "content_length", None)
        if cl is not None:
            return int(cl)
    except Exception:
        pass
    # Fallback: measure underlying stream without disturbing current position
    stream = file_storage.stream
    pos = stream.tell()
    stream.seek(0, os.SEEK_END)
    size = stream.tell()
    stream.seek(pos, os.SEEK_SET)
    return size

def get_daily_upload_dir():
    """Get daily subdirectory for organizing uploaded ZIP files by date."""
    today_str = datetime.now(timezone.utc).strftime("%Y_%m_%d")
    upload_daily = UPLOAD_DIR / today_str
    return upload_daily

@bp.route("/upload_files", methods=["GET"])
@roles_required(
    "fileUploader",
)
def upload_form():
    # Get available hospitals and lab units for the current user via shared eligibility helper
    allowed_lab_unit_ids = set(get_user_lab_unit_ids_no_admin_override(current_user.id) or [])
    if not allowed_lab_unit_ids:
        flash("No lab unit access.", "warning")
        return redirect(url_for("home.index"))

    from db_transaction_manager import transaction_scope

    with transaction_scope() as db:
        upload_options = get_user_upload_options_for_kind(db, current_user.id, UPLOAD_KIND_REMIDIO)
        lab_units = (
            db.query(LabUnit)
            .options(selectinload(LabUnit.hospital))
            .filter(LabUnit.id.in_(list(allowed_lab_unit_ids)))
            .order_by(LabUnit.name)
            .all()
        )
        profile_camera_ids = {camera_id for profile in upload_options.profiles for camera_id in profile["camera_ids"]}
        zip_cameras = (
            db.query(Camera)
            .filter(Camera.is_zip_upload_enabled.is_(True))
            .filter(Camera.id.in_(profile_camera_ids or {-1}))
            .order_by(Camera.name)
            .all()
        )
        hospital_ids = sorted({lu.hospital_id for lu in lab_units if lu.hospital_id is not None})
        if hospital_ids:
            hospitals = (
                db.query(Hospital)
                .options(selectinload(Hospital.lab_units))
                .filter(Hospital.id.in_(hospital_ids))
                .order_by(Hospital.name)
                .all()
            )
        else:
            hospitals = []

        # Extract lab_units data to avoid session issues in templates
        lab_units_data = [
            {
                'id': lu.id,
                'name': lu.name,
                'hospital_id': lu.hospital_id,
                'hospital': {
                    'id': lu.hospital.id,
                    'name': lu.hospital.name
                } if lu.hospital else None
            } for lu in lab_units
        ]

        # Extract hospitals data to avoid session issues in templates
        hospitals_data = [
            {
                'id': h.id,
                'name': h.name,
                'lab_units_count': len(h.lab_units) if hasattr(h, 'lab_units') else 0
            } for h in hospitals
        ]
        zip_cameras_data = [
            {
                'id': camera.id,
                'name': camera.name,
            } for camera in zip_cameras
        ]

    # Get recent ZIP uploads for display
    recent_uploads = get_recent_zip_uploads(limit=5, job_type="zip upload")

    with get_db_session() as settings_db:
        max_files = _get_int_setting(
            settings_db,
            "MAX_FILES_PER_UPLOAD",
            "MAX_FILES_PER_UPLOAD",
            int(current_app.config.get("MAX_FILES_PER_UPLOAD", 50)),
            min_value=1,
        )
        per_file_max_bytes = _get_int_setting(
            settings_db,
            "PER_FILE_MAX_BYTES",
            "PER_FILE_MAX_BYTES",
            int(current_app.config.get("PER_FILE_MAX_BYTES", 10 * 1024 * 1024)),
            min_value=1,
        )

    return render_template(
        "upload/upload_multi.html",
        per_file_mb=int(per_file_max_bytes / (1024 * 1024)),
        max_files=max_files,
        hospitals=hospitals_data,  # Use extracted data instead of objects
        lab_units=lab_units_data,   # Use extracted data instead of objects
        zip_cameras=zip_cameras_data,
        projects=upload_options.projects,
        upload_profiles=upload_options.profiles,
        recent_uploads=recent_uploads
    )

@bp.route("/upload", methods=["POST"])
@roles_required(
    "fileUploader",
)
def upload_files():
    per_file_default = int(current_app.config.get("PER_FILE_MAX_BYTES", 64 * 1024 * 1024))
    max_files_default = int(current_app.config.get("MAX_FILES_PER_UPLOAD", 50))

    with get_db_session() as db:
        per_file_max = _get_int_setting(db, "PER_FILE_MAX_BYTES", "PER_FILE_MAX_BYTES", per_file_default, min_value=1)
        max_files = _get_int_setting(db, "MAX_FILES_PER_UPLOAD", "MAX_FILES_PER_UPLOAD", max_files_default, min_value=1)

    # Validate hospital and lab unit selection
    try:
        hospital_id = int(request.form.get("hospital_id", 0))
        project_id = int(request.form.get("project_id", 0))
        lab_unit_id = int(request.form.get("lab_unit_id", 0))
        camera_id = int(request.form.get("camera_id", 0))
    except (ValueError, TypeError):
        flash("Invalid hospital, project, lab unit, or camera selection.", "danger")
        return redirect(url_for("remedio_zip_uploads.upload_form"))

    if hospital_id <= 0 or project_id <= 0 or lab_unit_id <= 0 or camera_id <= 0:
        flash("Please select a hospital, project, lab unit, and ZIP-enabled camera.", "danger")
        return redirect(url_for("remedio_zip_uploads.upload_form"))

    allowed_lab_unit_ids = set(get_user_lab_unit_ids_no_admin_override(current_user.id) or [])
    if not allowed_lab_unit_ids:
        flash("No lab unit access.", "warning")
        return redirect(url_for("remedio_zip_uploads.upload_form"))

    # Validate that the selected lab unit belongs to the selected hospital
    with get_db_session() as db:
        lab_unit = db.query(LabUnit).filter(
            LabUnit.id == lab_unit_id,
            LabUnit.hospital_id == hospital_id
        ).first()
        camera = db.query(Camera).filter(
            Camera.id == camera_id,
            Camera.is_zip_upload_enabled.is_(True),
        ).first()
        
        if not lab_unit:
            flash("Invalid hospital/lab unit combination.", "danger")
            return redirect(url_for("remedio_zip_uploads.upload_form"))
        if not camera:
            flash("Please select a ZIP-enabled camera.", "danger")
            return redirect(url_for("remedio_zip_uploads.upload_form"))
            
        # Validate that the current user has access to this lab unit
        if lab_unit_id not in allowed_lab_unit_ids:
            flash("You don't have access to the selected lab unit.", "danger")
            return redirect(url_for("remedio_zip_uploads.upload_form"))
        try:
            upload_profile = validate_remedio_upload_scope(
                db,
                current_user.id,
                project_id=project_id,
                lab_unit_id=lab_unit_id,
                camera_id=camera_id,
            )
        except UploadProfileError as exc:
            flash(exc.message, "danger")
            return redirect(url_for("remedio_zip_uploads.upload_form"))

    files = request.files.getlist("files")
    if not files:
        flash("No files uploaded.", "warning")
        return redirect(url_for("remedio_zip_uploads.upload_form"))

    if len(files) > max_files:
        flash(f"Too many files. Max allowed is {max_files}.", "danger")
        return redirect(url_for("remedio_zip_uploads.upload_form"))

    saved_paths: list[Path] = []
    rejected: list[str] = []

    # Get daily upload directory
    daily_upload_dir = get_daily_upload_dir()

    for f in files:
        fname = (f.filename or "").strip()
        if not fname:
            rejected.append("(empty filename)")
            continue
        # skip macOS resource forks and enforce .zip
        if fname.startswith("._"):
            rejected.append(f"{fname} (resource-fork file)")
            continue
        if not _allowed_zip(fname):
            rejected.append(f"{fname} (not a .zip)")
            continue
        if _file_size_bytes(f) > per_file_max:
            rejected.append(f"{fname} (> {int(per_file_max/1024/1024)} MB)")
            continue

        daily_upload_dir.mkdir(parents=True, exist_ok=True)
        save_path = _uniquify(daily_upload_dir, fname)
        try:
            # ensure stream is at start before saving
            try:
                f.stream.seek(0)
            except Exception:
                pass
            f.save(str(save_path))
            saved_paths.append(save_path)

            # Write sidecar metadata for uploader and IP
            try:
                meta_dir = daily_upload_dir.parent.parent / "upload_meta"
                meta_dir.mkdir(parents=True, exist_ok=True)
                xff = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
                ip = xff or (request.remote_addr or "-")
                meta = {
                    "filename": save_path.name,
                    "uploaded_at": datetime.now(timezone.utc).isoformat() + "Z",
                    "uploader_username": getattr(current_user, "username", None) or "-",
                    "uploader_id": getattr(current_user, "id", None),
                    "ip": ip,
                    "user_agent": request.headers.get("User-Agent", "-"),
                    "hospital_id": hospital_id,
                    "lab_unit_id": lab_unit_id,
                    "project_id": upload_profile.project_id,
                    "upload_profile_id": upload_profile.profile_id,
                    "default_disease_id": upload_profile.default_disease_id,
                    "camera_id": camera_id,
                }
                with open(meta_dir / f"{save_path.name}.json", "w", encoding="utf-8") as mf:
                    json.dump(meta, mf, ensure_ascii=False)
            except Exception:
                # Metadata logging should not block upload; ignore errors
                pass
        except Exception as ex:
            rejected.append(f"{fname} (save failed: {ex})")

    if not saved_paths:
        flash("All files were rejected (not ZIP or too large).", "danger")
        return redirect(url_for("remedio_zip_uploads.upload_form"))

    # Create Job in DB and queue background work
    # Capture uploader identity and client IP
    xff = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
    ip = xff or (request.remote_addr or "-")
    uploader_username = getattr(current_user, "username", None)
    uploader_user_id = getattr(current_user, "id", None)
    job_token = db_create_job(
        [p.name for p in saved_paths],
        rejected,
        uploader_user_id=uploader_user_id,
        uploader_username=uploader_username,
        uploader_ip=ip,
        lab_unit_id=lab_unit_id,
        project_id=upload_profile.project_id,
        upload_type="zip upload",
        upload_kind=UPLOAD_KIND_REMIDIO,
        upload_profile_id=upload_profile.profile_id,
    )
    upload_context = {
        "hospital_id": hospital_id,
        "lab_unit_id": lab_unit_id,
        "project_id": upload_profile.project_id,
        "upload_profile_id": upload_profile.profile_id,
        "default_disease_id": upload_profile.default_disease_id,
        "camera_id": camera_id,
    }
    queue_job(
        current_app,
        job_token,
        saved_paths,
        user_id=uploader_user_id,
        hospital_id=hospital_id,
        upload_context=upload_context,
    )

    flash(f"Queued {len(saved_paths)} file(s) for processing. Rejected: {len(rejected)}", "info")
    return redirect(url_for("jobs.job_status_page", job_token=job_token))
