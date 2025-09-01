# direct_uploads/uploads.py

import os, uuid, hashlib, magic
from datetime import datetime
from werkzeug.utils import secure_filename
from flask import request, render_template, redirect, url_for, flash, current_app
from flask_login import current_user
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from . import bp
from .utils import with_session
from auth.roles import roles_required
from models import (
    User, LabUnit, Hospital, DirectImageUpload,
    Camera, Disease, Area, Job, JobItem
)

from .paths import get_upload_dirs, uniquify


def _to_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


@bp.route("/direct/upload", methods=["GET", "POST"])
@roles_required('contributor', 'data_manager', 'admin')
def upload():
    with with_session() as db_session:
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
                current_user.username, current_user.id, request.remote_addr
            )
            current_app.logger.info(
                "Upload parameters - Hospital:%s LabUnit:%s Camera:%s Disease:%s Area:%s Mydriatic:%s",
                hospital_id, lab_unit_id, camera_id, disease_id, area_id, is_mydriatic
            )

            # ---- limits & allowed types ----
            MAX_FILES_ALLOWED   = int(os.getenv("DIRECT_UPLOAD_MAX_FILES", 100))
            MAX_FILE_SIZE_MB    = int(os.getenv("DIRECT_UPLOAD_MAX_FILE_SIZE_MB", 5))
            MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
            ALLOWED_MIMETYPES   = [m.strip() for m in os.getenv(
                "DIRECT_UPLOAD_ALLOWED_MIMETYPES", "image/jpeg,image/png"
            ).split(",")]

            # ---- validate required fields ----
            if not all([hospital_id, lab_unit_id, camera_id, disease_id, area_id]):
                current_app.logger.warning("Direct upload failed: missing fields for user %s (%s)",
                                           current_user.username, current_user.id)
                flash("All fields are required.", "danger")
                return redirect(url_for("direct_uploads.upload"), code=303)

            hospital = db_session.get(Hospital, hospital_id)
            lab_unit = db_session.get(LabUnit, lab_unit_id)
            camera   = db_session.get(Camera,   camera_id)
            disease  = db_session.get(Disease,  disease_id)
            area     = db_session.get(Area,     area_id)

            if not all([hospital, lab_unit, camera, disease, area]):
                current_app.logger.warning("Direct upload failed: invalid selection for user %s (%s)",
                                           current_user.username, current_user.id)
                flash("Invalid selection for one or more fields.", "danger")
                return redirect(url_for("direct_uploads.upload"), code=303)

            # Optional consistency: lab unit must belong to hospital
            if getattr(lab_unit, "hospital_id", None) != hospital.id:
                flash("Selected Lab Unit does not belong to the selected Hospital.", "danger")
                return redirect(url_for("direct_uploads.upload"), code=303)

            # ---- job bookkeeping ----
            job_token = str(uuid.uuid4())
            new_job = Job(
                token=job_token,
                status="processing",
                uploader_user_id=current_user.id,
                uploader_username=current_user.username,
                uploader_ip=request.remote_addr
            )
            db_session.add(new_job)
            db_session.flush()
            current_app.logger.info("Created new job %s for user %s (%s)",
                                    new_job.id, current_user.username, current_user.id)

            # ---- dirs for this user/day ----
            orig_dir, edited_dir, dup_dir, folder_rel = get_upload_dirs(current_user.id)
    

            # ---- process files ----
            files = files[:MAX_FILES_ALLOWED]  # hard-cap
            if not files:
                flash("No files selected.", "warning")
                return redirect(url_for("direct_uploads.upload"), code=303)

            current_app.logger.info("Processing %s files for upload", len(files))

            job_items = []

            for file in files:
                filename = secure_filename(file.filename or "")
                state, detail = "queued", ""

                if not filename:
                    state, detail = "error", "No selected file"
                    current_app.logger.warning("File upload error: no selected file")
                else:
                    content = file.read()
                    size = len(content)
                    current_app.logger.info("Processing file: %s (%s bytes)", filename, size)

                    if size > MAX_FILE_SIZE_BYTES:
                        state, detail = "error", f"File too large (max {MAX_FILE_SIZE_MB}MB)"
                        current_app.logger.warning("Too large: %s bytes for %s", size, filename)
                    else:
                        mime_type = magic.from_buffer(content, mime=True)
                        if mime_type not in ALLOWED_MIMETYPES:
                            state, detail = "error", f"Invalid file type: {mime_type}. Only JPG/PNG allowed."
                            current_app.logger.warning("Invalid type %s for %s", mime_type, filename)
                        else:
                            md5_hash = hashlib.md5(content).hexdigest()
                            existing = db_session.execute(
                                select(DirectImageUpload).filter_by(file_hash=md5_hash)
                            ).scalar_one_or_none()

                            if existing:
                                # save a copy to dup folder (no DB row)
                                path = uniquify(dup_dir, filename)
                                path.write_bytes(content)
                                state, detail = "error", "Duplicate file"
                                current_app.logger.info("Duplicate: %s", filename)
                            else:
                                # per-request quota (optional; your config key)
                                if current_user.file_upload_count >= current_app.config.get("MAX_FILES_PER_UPLOAD", 50):
                                    state, detail = "error", "Upload quota exceeded"
                                    current_app.logger.warning("Quota exceeded for user %s (%s)",
                                                               current_user.username, current_user.id)
                                else:
                                    # write original
                                    dest = uniquify(orig_dir, filename)
                                    dest.write_bytes(content)

                                    # create DB row (folder-based; store basenames only)
                                    db_session.add(DirectImageUpload(
                                        filename=dest.name,                 # basename stored
                                        folder_rel=folder_rel,    
                                        edited_filename=None,               # not yet
                                        file_hash=md5_hash,
                                        uploader_id=current_user.id,
                                        hospital_id=hospital.id,
                                        lab_unit_id=lab_unit.id,
                                        camera_id=camera.id,
                                        disease_id=disease.id,
                                        area_id=area.id,
                                        is_mydriatic=is_mydriatic,
                                    ))
                                    current_user.file_upload_count += 1
                                    state, detail = "completed", "File uploaded successfully"
                                    current_app.logger.info("Uploaded: %s", dest.name)

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
            new_job.status = "completed" if all(i.state == "completed" for i in job_items) else "error"
            db_session.commit()

            ok = sum(1 for i in job_items if i.state == "completed")
            err = len(job_items) - ok
            current_app.logger.info("Job %s done. Success:%s Errors:%s", new_job.id, ok, err)

            flash("Upload process initiated. Check status for details.", "info")
            return redirect(url_for("direct_uploads.upload_processing", job_id=new_job.id), code=303)

        # ---------------- GET: build form data ----------------
        current_app.logger.info("Direct upload page accessed by %s (%s)", current_user.username, current_user.id)

        user = db_session.get(User, current_user.id)  # attaches to session
        user_lab_unit_ids = {lu.id for lu in user.lab_units}

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

        return render_template("direct_uploads/upload.html",
                               hospitals=hospitals, lab_units=lab_units,
                               cameras=cameras, diseases=diseases, areas=areas)


@bp.route("/direct/upload/processing/<int:job_id>", methods=["GET"])
@roles_required('contributor', 'data_manager', 'admin')
def upload_processing(job_id):
    return render_template("direct_uploads/upload_processing.html", job_id=job_id)
