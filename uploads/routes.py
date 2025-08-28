# uploads/routes.py
import os
from pathlib import Path
from datetime import datetime
from flask import (
    render_template, request, redirect, url_for, flash, current_app
)
from werkzeug.utils import secure_filename
from models import Session, UPLOAD_DIR
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
    pos = file_storage.stream.tell()
    file_storage.stream.seek(0, os.SEEK_END)
    size = file_storage.stream.tell()
    file_storage.stream.seek(pos, os.SEEK_SET)
    return size

@bp.route("/upload_files", methods=["GET"])
@roles_required("admin", "fileUploader")
def upload_form():
    return render_template(
        "upload_multi.html",
        per_file_mb=int(current_app.config["PER_FILE_MAX_BYTES"] / (1024 * 1024)),
        max_files=current_app.config["MAX_FILES_PER_UPLOAD"],
    )

@bp.route("/upload", methods=["POST"])
@roles_required("admin", "fileUploader")
def upload_files():
    per_file_max = current_app.config["PER_FILE_MAX_BYTES"]
    max_files = current_app.config["MAX_FILES_PER_UPLOAD"]

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
        if not _allowed_zip(fname):
            rejected.append(f"{fname} (not a .zip)")
            continue
        if _file_size_bytes(f) > per_file_max:
            rejected.append(f"{fname} (> {int(per_file_max/1024/1024)} MB)")
            continue

        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        save_path = _uniquify(UPLOAD_DIR, fname)
        f.seek(0)
        f.save(str(save_path))
        saved_paths.append(save_path)

    if not saved_paths:
        flash("All files were rejected (not ZIP or too large).", "danger")
        return redirect(url_for("uploads.upload_form"))

    # Create Job in DB and queue background work
    job_token = db_create_job([p.name for p in saved_paths], rejected)
    queue_job(current_app, job_token, saved_paths)

    flash(f"Queued {len(saved_paths)} file(s) for processing. Rejected: {len(rejected)}", "info")
    return redirect(url_for("jobs.job_status_page", job_token=job_token))
