import os
import uuid
import hashlib
import magic
from datetime import datetime
from typing import List, Optional, Tuple

from flask import (
    request,
    render_template,
    redirect,
    url_for,
    flash,
    current_app,
)
from flask_login import current_user
from sqlalchemy import select, func

from . import bp
from auth.roles import roles_required
from utils.utils import with_session
from utils.fileUtils import get_upload_dirs
from utils.upload_eligibility import get_user_lab_unit_ids
from utils.utils2 import uniquify
from models import (
    User,
    LabUnit,
    Hospital,
    DirectImageUpload,
    DirectImageVerify,
    Camera,
    Disease,
    Area,
    Job,
    JobItem,
)
from services.taskCreationServices import ensure_task


def _to_int(value: Optional[str]) -> Optional[int]:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


@bp.route("/direct/pregraded", methods=["GET", "POST"])
@roles_required("fileUploader", "optometrist", "data_manager", "admin")
def pregraded_upload():
    with with_session() as db_session:
        if request.method == "POST":
            hospital_id = _to_int(request.form.get("hospital_id"))
            lab_unit_id = _to_int(request.form.get("lab_unit_id"))
            camera_id = _to_int(request.form.get("camera_id"))
            disease_id = _to_int(request.form.get("disease_id"))
            area_id = _to_int(request.form.get("area_id"))
            dataset_label = (request.form.get("dataset_label") or "").strip()
            is_mydriatic = request.form.get("is_mydriatic") == "on"
            files = request.files.getlist("files")

            MAX_FILES_ALLOWED = int(os.getenv("DIRECT_UPLOAD_MAX_FILES", 100))
            MAX_FILE_SIZE_MB = int(os.getenv("DIRECT_UPLOAD_MAX_FILE_SIZE_MB", 5))
            MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
            ALLOWED_MIMETYPES = [
                m.strip()
                for m in os.getenv(
                    "DIRECT_UPLOAD_ALLOWED_MIMETYPES", "image/jpeg,image/png"
                ).split(",")
            ]

            if not all([hospital_id, lab_unit_id, camera_id, disease_id, area_id]):
                flash("All fields are required.", "danger")
                return redirect(url_for("direct_uploads.pregraded_upload"), code=303)

            hospital = db_session.get(Hospital, hospital_id)
            lab_unit = db_session.get(LabUnit, lab_unit_id)
            camera = db_session.get(Camera, camera_id)
            disease = db_session.get(Disease, disease_id)
            area = db_session.get(Area, area_id)

            if not all([hospital, lab_unit, camera, disease, area]):
                flash("Invalid selection for one or more fields.", "danger")
                return redirect(url_for("direct_uploads.pregraded_upload"), code=303)

            if getattr(lab_unit, "hospital_id", None) != hospital.id:
                flash(
                    "Selected Lab Unit does not belong to the selected Hospital.",
                    "danger",
                )
                return redirect(url_for("direct_uploads.pregraded_upload"), code=303)

            is_admin = current_user.has_role("admin")
            is_manager = current_user.has_role("data_manager")
            if not (is_admin or is_manager):
                allowed_lab_units = get_user_lab_unit_ids(current_user.id)
                if lab_unit.id not in allowed_lab_units:
                    flash("You don't have access to the selected lab unit.", "danger")
                    return redirect(url_for("direct_uploads.pregraded_upload"), code=303)

            job_token = str(uuid.uuid4())
            new_job = Job(
                token=job_token,
                status="processing",
                uploader_user_id=current_user.id,
                uploader_username=current_user.username,
                uploader_ip=request.remote_addr,
                lab_unit_id=lab_unit.id,
                rejected_summary=dataset_label or None,
            )
            db_session.add(new_job)
            db_session.flush()

            orig_dir, _, _, folder_rel = get_upload_dirs(current_user.id)

            files = files[:MAX_FILES_ALLOWED]
            if not files:
                flash("No files selected.", "warning")
                return redirect(url_for("direct_uploads.pregraded_upload"), code=303)

            job_items: List[JobItem] = []
            pending_tasks: List[Tuple[str, JobItem]] = []

            for file_storage in files:
                filename = (file_storage.filename or "").strip()
                state = "queued"
                detail = ""

                if not filename:
                    state = "error"
                    detail = "No selected file"
                else:
                    content = file_storage.read()
                    size = len(content)

                    if size > MAX_FILE_SIZE_BYTES:
                        state = "error"
                        detail = f"File too large (max {MAX_FILE_SIZE_MB}MB)"
                    else:
                        mime_type = magic.from_buffer(content, mime=True)
                        if mime_type not in ALLOWED_MIMETYPES:
                            state = "error"
                            detail = (
                                f"Invalid file type: {mime_type}. Only JPG/PNG allowed."
                            )
                        else:
                            try:
                                md5_hash = hashlib.md5(content).hexdigest()
                                dest = uniquify(orig_dir, filename)
                                dest.write_bytes(content)

                                direct_upload = DirectImageUpload(
                                    original_filename=filename,
                                    filename=dest.name,
                                    folder_rel=folder_rel,
                                    edited_filename=None,
                                    file_hash=md5_hash,
                                    content_hash=md5_hash,
                                    uploader_id=current_user.id,
                                    hospital_id=hospital.id,
                                    lab_unit_id=lab_unit.id,
                                    camera_id=camera.id,
                                    disease_id=disease.id,
                                    area_id=area.id,
                                    is_mydriatic=is_mydriatic,
                                    is_pregraded=True,
                                )
                                db_session.add(direct_upload)
                                db_session.flush()

                                verification_remark = (
                                    dataset_label
                                    or f"Pre-graded upload on {datetime.utcnow():%Y-%m-%d}"
                                )

                                verification = (
                                    db_session.execute(
                                        select(DirectImageVerify).where(
                                            DirectImageVerify.image_upload_id
                                            == direct_upload.id
                                        )
                                    ).scalar_one_or_none()
                                )
                                if verification:
                                    verification.verified_status = "verified"
                                    verification.remarks = verification_remark
                                    verification.verified_by_id = current_user.id
                                    verification.verified_at = func.now()
                                else:
                                    db_session.add(
                                        DirectImageVerify(
                                            image_upload_id=direct_upload.id,
                                            verified_status="verified",
                                            remarks=verification_remark,
                                            verified_by_id=current_user.id,
                                            verified_at=func.now(),
                                        )
                                    )

                                state = "pending"
                                detail = "Stored; creating grading task…"
                                pending_tasks.append((direct_upload.uuid, None))  # placeholder for job item
                                current_user.file_upload_count += 1
                            except Exception as processing_error:  # noqa: BLE001
                                current_app.logger.exception(
                                    "Failed to store pre-graded image %s", filename
                                )
                                state = "error"
                                detail = f"Processing failed: {processing_error}"

                job_item = JobItem(
                    job_id=new_job.id,
                    filename=filename,
                    state=state,
                    detail=detail,
                    uploader_user_id=current_user.id,
                    uploader_username=current_user.username,
                    uploader_ip=request.remote_addr,
                )
                job_items.append(job_item)
                if state == "pending":
                    pending_tasks[-1] = (pending_tasks[-1][0], job_item)

            db_session.add_all(job_items)
            db_session.commit()

            # Create tasks using a fresh session to ensure committed data is visible
            for uuid_value, job_item in pending_tasks:
                try:
                    ensure_task(uuid_value, disease_id)
                    job_item.state = "completed"
                    job_item.detail = "Imported with pre-graded task"
                except Exception as task_error:  # noqa: BLE001
                    current_app.logger.exception(
                        "Failed to ensure grading task for pre-graded image %s",
                        uuid_value,
                    )
                    job_item.state = "error"
                    job_item.detail = f"Task creation failed: {task_error}"

            successful = sum(1 for item in job_items if item.state == "completed")
            errors = len(job_items) - successful
            new_job.status = "completed" if errors == 0 else "error"
            new_job.error = (
                None
                if errors == 0
                else f"{errors} of {len(job_items)} files encountered issues."
            )
            db_session.commit()

            flash(
                "Pre-graded upload processed. Review job status for details.",
                "info",
            )
            return redirect(
                url_for("direct_uploads.upload_processing", job_id=new_job.id),
                code=303,
            )

        user = db_session.get(User, current_user.id)
        user_lab_unit_ids = {lu.id for lu in user.lab_units}

        lab_units = (
            db_session.execute(
                select(LabUnit)
                .where(LabUnit.id.in_(user_lab_unit_ids))
                .order_by(LabUnit.id)
            )
            .scalars()
            .all()
        )
        accessible_hospital_ids = {lu.hospital_id for lu in lab_units}
        hospitals = (
            db_session.execute(
                select(Hospital)
                .where(Hospital.id.in_(accessible_hospital_ids))
                .order_by(Hospital.name)
            )
            .scalars()
            .all()
        )
        cameras = (
            db_session.execute(select(Camera).order_by(Camera.name)).scalars().all()
        )
        diseases = (
            db_session.execute(select(Disease).order_by(Disease.name))
            .scalars()
            .all()
        )
        areas = (
            db_session.execute(select(Area).order_by(Area.name)).scalars().all()
        )

        return render_template(
            "direct_uploads/pregraded_upload.html",
            hospitals=hospitals,
            lab_units=lab_units,
            cameras=cameras,
            diseases=diseases,
            areas=areas,
        )
