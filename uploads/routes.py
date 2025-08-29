# uploads/routes.py
import os
from pathlib import Path
from datetime import datetime
from flask import (
    render_template, request, redirect, url_for, flash, current_app
)
from flask_login import current_user
from werkzeug.utils import secure_filename
from models import Session, UPLOAD_DIR
import json
from job_store import db_create_job
from worker import queue_job
from . import bp
from auth.roles import roles_required


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

@bp.route("/upload_files", methods=["GET"])
@roles_required("admin", "fileUploader")
def upload_form():
    return render_template(
        "upload/upload_multi.html",
        per_file_mb=int(current_app.config["PER_FILE_MAX_BYTES"] / (1024 * 1024)),
        max_files=current_app.config["MAX_FILES_PER_UPLOAD"],
    )

@bp.route("/upload", methods=["POST"])
@roles_required("admin", "fileUploader")
def upload_files():
    per_file_max = int(current_app.config.get("PER_FILE_MAX_BYTES", 64 * 1024 * 1024))
    max_files = int(current_app.config.get("MAX_FILES_PER_UPLOAD", 50))

    files = request.files.getlist("files")
    if not files:
        flash("No files uploaded.", "warning")
        return redirect(url_for("uploads.upload_form"))

    if len(files) > max_files:
        flash(f"Too many files. Max allowed is {max_files}.", "danger")
        return redirect(url_for("uploads.upload_form"))

    saved_paths: list[Path] = []
    rejected: list[str] = []

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

        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        save_path = _uniquify(UPLOAD_DIR, fname)
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
                meta_dir = UPLOAD_DIR.parent / "upload_meta"
                meta_dir.mkdir(parents=True, exist_ok=True)
                xff = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
                ip = xff or (request.remote_addr or "-")
                meta = {
                    "filename": save_path.name,
                    "uploaded_at": datetime.utcnow().isoformat() + "Z",
                    "uploader_username": getattr(current_user, "username", None) or "-",
                    "uploader_id": getattr(current_user, "id", None),
                    "ip": ip,
                    "user_agent": request.headers.get("User-Agent", "-"),
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
        return redirect(url_for("uploads.upload_form"))

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
    )
    queue_job(current_app, job_token, saved_paths)

    flash(f"Queued {len(saved_paths)} file(s) for processing. Rejected: {len(rejected)}", "info")
    return redirect(url_for("jobs.job_status_page", job_token=job_token))
