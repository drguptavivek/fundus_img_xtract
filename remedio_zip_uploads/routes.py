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
from models import Hospital, LabUnit, Session, UPLOAD_DIR
import json
from job_store import db_create_job
from worker import queue_job
from . import bp
from auth.roles import roles_required
from utils.upload_eligibility import get_user_lab_unit_ids
from utils.jobUtils import get_recent_zip_uploads


ALLOWED_EXT = {"zip"}

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
@roles_required("admin", "fileUploader", "optometrist", "data_manager")
def upload_form():
    # Get available hospitals and lab units for the current user via shared eligibility helper
    allowed_lab_unit_ids = get_user_lab_unit_ids(current_user.id)

    db = Session()
    try:
        if allowed_lab_unit_ids:
            lab_units = (
                db.query(LabUnit)
                .options(selectinload(LabUnit.hospital))
                .filter(LabUnit.id.in_(list(allowed_lab_unit_ids)))
                .order_by(LabUnit.name)
                .all()
            )
            hospital_ids = sorted({lu.hospital_id for lu in lab_units if lu.hospital_id is not None})
            if hospital_ids:
                hospitals = (
                    db.query(Hospital)
                    .filter(Hospital.id.in_(hospital_ids))
                    .order_by(Hospital.name)
                    .all()
                )
            else:
                hospitals = []
        else:
            lab_units = []
            hospitals = []
    finally:
        db.close()

    # Get recent ZIP uploads for display
    recent_uploads = get_recent_zip_uploads(limit=5, job_type="zip upload")
    
    return render_template(
        "upload/upload_multi.html",
        per_file_mb=int(current_app.config["PER_FILE_MAX_BYTES"] / (1024 * 1024)),
        max_files=current_app.config["MAX_FILES_PER_UPLOAD"],
        hospitals=hospitals,
        lab_units=lab_units,
        recent_uploads=recent_uploads
    )

@bp.route("/upload", methods=["POST"])
@roles_required("admin", "fileUploader", "optometrist", "data_manager")
def upload_files():
    per_file_max = int(current_app.config.get("PER_FILE_MAX_BYTES", 64 * 1024 * 1024))
    max_files = int(current_app.config.get("MAX_FILES_PER_UPLOAD", 50))

    # Validate hospital and lab unit selection
    try:
        hospital_id = int(request.form.get("hospital_id", 0))
        lab_unit_id = int(request.form.get("lab_unit_id", 0))
    except (ValueError, TypeError):
        flash("Invalid hospital or lab unit selection.", "danger")
        return redirect(url_for("remedio_zip_uploads.upload_form"))

    if hospital_id <= 0 or lab_unit_id <= 0:
        flash("Please select both a hospital and a lab unit.", "danger")
        return redirect(url_for("remedio_zip_uploads.upload_form"))

    allowed_lab_unit_ids = get_user_lab_unit_ids(current_user.id)

    # Validate that the selected lab unit belongs to the selected hospital
    db = Session()
    try:
        lab_unit = db.query(LabUnit).filter(
            LabUnit.id == lab_unit_id,
            LabUnit.hospital_id == hospital_id
        ).first()
        
        if not lab_unit:
            flash("Invalid hospital/lab unit combination.", "danger")
            return redirect(url_for("remedio_zip_uploads.upload_form"))
            
        # Validate that the current user has access to this lab unit
        if allowed_lab_unit_ids and lab_unit_id not in allowed_lab_unit_ids:
            flash("You don't have access to the selected lab unit.", "danger")
            return redirect(url_for("remedio_zip_uploads.upload_form"))
        if not allowed_lab_unit_ids and not current_user.has_role('admin'):
            flash("You don't have access to any lab units. Contact an administrator.", "danger")
            return redirect(url_for("remedio_zip_uploads.upload_form"))
    finally:
        db.close()

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
        upload_type="zip upload",
    )
    queue_job(current_app, job_token, saved_paths)

    flash(f"Queued {len(saved_paths)} file(s) for processing. Rejected: {len(rejected)}", "info")
    return redirect(url_for("jobs.job_status_page", job_token=job_token))
