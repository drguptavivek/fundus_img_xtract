#screenings/routes.py
from math import ceil
import re
from datetime import datetime
from flask import abort, render_template, request, current_app, url_for, flash, redirect
from flask_login import current_user
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy import and_, or_

from auth.roles import roles_required
from utils.rate_limiter import rate_limit
from . import bp
from models import (
    PatientEncounters, LabUnit, Hospital,
    EncounterFilePDF, DiabeticRetinopathyReport, GlaucomaReport, ZipFile
)
from db_transaction_manager import get_db_session
from utils.upload_eligibility import get_user_lab_unit_ids
from utils.log_sanitize import sanitize_log_value
from utils.rate_limiter import rate_limit

@bp.route("/", methods=["GET"])
@roles_required("admin", "fileUploader", "optometrist", "data_manager")
@rate_limit("120 per minute")
def list_screenings():
    # Query params
    page = request.args.get("page", default=1, type=int) or 1
    q = (request.args.get("q") or "").strip()
    per_page = int(current_app.config.get("SCREENINGS_PAGE_SIZE", 50)) or 50
    page = max(1, page)
    per_page = max(1, per_page)

    allowed_lab_unit_ids = get_user_lab_unit_ids(current_user.id)
    is_admin_like = current_user.has_role("admin")

    with get_db_session() as db:
        # Base query with eager loading of lab_unit and hospital relationships
        base_q = (
            db.query(PatientEncounters)
            .options(
                joinedload(PatientEncounters.zip_file),
                selectinload(PatientEncounters.glaucoma_reports),
                selectinload(PatientEncounters.dr_reports),
                selectinload(PatientEncounters.encounter_files),
                selectinload(PatientEncounters.encounter_file_pdfs),
                joinedload(PatientEncounters.lab_unit).joinedload(LabUnit.hospital)
            )
            .order_by(
                PatientEncounters.capture_date_dt.desc().nullslast(),
                PatientEncounters.id.desc(),
            )
        )

        if is_admin_like:
            pass
        elif allowed_lab_unit_ids:
            base_q = base_q.filter(PatientEncounters.lab_unit_id.in_(list(allowed_lab_unit_ids)))
        else:
            return render_template(
                "screenings/list.html",
                items=[],
                page=page,
                per_page=per_page,
                total=0,
                total_pages=1,
                has_prev=False,
                has_next=False,
                prev_url=None,
                next_url=None,
                q=q,
            )

        # --- Search by patient_id or name ---
        # PatientEncounters has columns 'patient_id' and 'name'  :contentReference[oaicite:0]{index=0}
        if q:
            tokens = [t for t in re.split(r"\s+", q) if t]
            for t in tokens:
                # If token looks like a date (YYYY-MM-DD), also match on capture_date_dt
                dt = None
                try:
                    if re.match(r"^\d{4}-\d{2}-\d{2}$", t):
                        dt = datetime.strptime(t, "%Y-%m-%d").date()
                except Exception:
                    dt = None
                pat = f"%{t}%"
                if dt is not None:
                    base_q = base_q.filter(
                        or_(
                            PatientEncounters.patient_id.ilike(pat),
                            PatientEncounters.name.ilike(pat),
                            PatientEncounters.capture_date_dt == dt,
                        )
                    )
                else:
                    base_q = base_q.filter(
                        or_(
                            PatientEncounters.patient_id.ilike(pat),
                            PatientEncounters.name.ilike(pat),
                        )
                    )

        # Total rows AFTER filters
        total = base_q.count()
        total_pages = max(1, ceil(total / per_page)) if total else 1

        # Clamp page
        if page > total_pages:
            page = total_pages

        # Page items with eager loads
        items = (
            base_q
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )

        has_prev = page > 1
        has_next = page < total_pages

        return render_template(
            "screenings/list.html",
            items=items,
            page=page,
            per_page=per_page,
            total=total,
            total_pages=total_pages,
            has_prev=has_prev,
            has_next=has_next,
            # keep q in pagination links
            prev_url=url_for("screenings.list_screenings", page=page-1, q=q) if has_prev else None,
            next_url=url_for("screenings.list_screenings", page=page+1, q=q) if has_next else None,
            q=q,
        )


@bp.route("/<int:encounter_id>", methods=["GET"])
@roles_required("admin", "fileUploader", "optometrist", "data_manager")
@rate_limit("120 per minute")
def screening_detail(encounter_id: int):
    IMAGE_EXTS = {"jpg", "jpeg", "png", "webp", "tif", "tiff", "bmp"}

    allowed_lab_unit_ids = get_user_lab_unit_ids(current_user.id)
    is_admin_like = current_user.has_role("admin")

    with get_db_session() as db:
        encounter = (
            db.query(PatientEncounters)
            .options(
                joinedload(PatientEncounters.zip_file),
                selectinload(PatientEncounters.encounter_files),
                selectinload(PatientEncounters.dr_reports),
                selectinload(PatientEncounters.glaucoma_reports),
                selectinload(PatientEncounters.encounter_file_pdfs),
                joinedload(PatientEncounters.lab_unit).joinedload(LabUnit.hospital)
            )
            .filter(PatientEncounters.id == encounter_id)
            .first()
        )
        if not encounter:
            abort(404, description="Encounter not found")

        if (not is_admin_like) and encounter.lab_unit_id and allowed_lab_unit_ids and encounter.lab_unit_id not in allowed_lab_unit_ids:
            abort(403)

        # Prev/Next (global ordering: capture_date DESC, id DESC)
        prev_enc = (
            db.query(PatientEncounters)
            .filter(
                or_(
                    PatientEncounters.capture_date > encounter.capture_date,
                    and_(
                        PatientEncounters.capture_date == encounter.capture_date,
                        PatientEncounters.id > encounter.id,
                    ),
                )
            )
            .order_by(PatientEncounters.capture_date.asc(), PatientEncounters.id.asc())
            .first()
        )
        next_enc = (
            db.query(PatientEncounters)
            .filter(
                or_(
                    PatientEncounters.capture_date < encounter.capture_date,
                    and_(
                        PatientEncounters.capture_date == encounter.capture_date,
                        PatientEncounters.id < encounter.id,
                    ),
                )
            )
            .order_by(PatientEncounters.capture_date.desc(), PatientEncounters.id.desc())
            .first()
        )
        prev_url = url_for("screenings.screening_detail", encounter_id=prev_enc.id) if prev_enc else None
        next_url = url_for("screenings.screening_detail", encounter_id=next_enc.id) if next_enc else None

        # Images only from encounter_files
        images = []
        for ef in (encounter.encounter_files or []):
            ft = (ef.file_type or "").lower().strip()
            ext = ef.filename.rsplit(".", 1)[-1].lower() if ef.filename and "." in ef.filename else ""
            if ft.startswith("image/") or ext in IMAGE_EXTS:
                images.append(ef)

        # Reports (for left-side buttons)
        dr_reports = encounter.dr_reports or []
        gl_reports = encounter.glaucoma_reports or []

        gallery_id = f"pswp-gallery-enc-{encounter.id}"

        return render_template(
            "screenings/detail.html",
            encounter=encounter,
            images=images,
            dr_reports=dr_reports,
            gl_reports=gl_reports,
            back_url=url_for("screenings.list_screenings"),
            prev_url=prev_url,
            next_url=next_url,
            gallery_id=gallery_id,
        )


@bp.route("/reprocess_pdf/<int:encounter_id>", methods=["POST"])
@roles_required("admin", "data_manager")
def reprocess_pdf(encounter_id: int):
    """Reset OCR processing flag for a specific encounter to allow reprocessing."""
    with get_db_session() as db:
        # Get the encounter
        encounter = db.query(PatientEncounters).filter(PatientEncounters.id == encounter_id).first()
        if not encounter:
            flash("Encounter not found", "danger")
            return redirect(url_for("screenings.list_screenings"))

        allowed_lab_unit_ids = get_user_lab_unit_ids(current_user.id)
        is_admin_like = current_user.has_role("admin")

        # Admin override or strict lab unit check (data_manager role is not exempt from hospital scoping unless global admin logic implemented elsewhere, but here rely on allowed_lab_unit_ids)
        # Note: 'data_manager' is often treated as local admin. If they have lab_units, restrict them.
        if (not is_admin_like) or (allowed_lab_unit_ids and encounter.lab_unit_id not in allowed_lab_unit_ids):
             # Actually, if is_admin_like is true, we might still want to restrict if they are not GLOBAL admin.
             # The existing pattern check:
             # if (not is_admin_like) and encounter.lab_unit_id and allowed_lab_unit_ids and encounter.lab_unit_id not in allowed_lab_unit_ids:
             # However, roles_required("admin", "data_manager") means only these roles access.
             # If a data_manager is scoped to a hospital, allowed_lab_unit_ids will be populated.
             if encounter.lab_unit_id and allowed_lab_unit_ids and encounter.lab_unit_id not in allowed_lab_unit_ids:
                 abort(403)

        # Find PDF files for this encounter
        pdf_files = db.query(EncounterFilePDF).filter(
            EncounterFilePDF.patient_encounter_id == encounter_id
        ).all()

        if not pdf_files:
            flash("No PDF files found for this encounter", "warning")
            return redirect(url_for("screenings.screening_detail", encounter_id=encounter_id))

        # Check for existing reports
        dr_reports = db.query(DiabeticRetinopathyReport).filter_by(
            patient_encounter_id=encounter_id
        ).all()

        gl_reports = db.query(GlaucomaReport).filter_by(
            patient_encounter_id=encounter_id
        ).all()

        reports_exist = len(dr_reports) > 0 or len(gl_reports) > 0

        # Reset OCR processed flag for all PDFs
        reset_count = 0
        for pdf_file in pdf_files:
            if pdf_file.ocr_processed:
                pdf_file.ocr_processed = False
                db.add(pdf_file)
                reset_count += 1

        if reset_count > 0:
            db.commit()
            message = f"Reset OCR processing for {reset_count} PDF file(s)"
            if reports_exist:
                message += ". Note: Existing reports were not deleted - you may want to delete them manually if needed"
            flash(message, "success")
        else:
            flash("PDF files were already marked for processing", "info")

        # Queue the PDF processing job
        from job_store import db_create_job
        from worker import queue_job

        job_token = db_create_job(
            [f"Reprocess encounter {encounter_id} (Patient: {encounter.patient_id})"],
            [],
            uploader_user_id=current_user.id,
            uploader_username=getattr(current_user, 'username', None),
            uploader_ip=request.remote_addr,
            lab_unit_id=encounter.lab_unit_id,
            upload_type="pdf reprocess",
        )

        hospital_id = getattr(encounter, "hospital_id", None)
        queue_job(current_app, job_token, [], user_id=current_user.id, hospital_id=hospital_id)

        flash(f"PDF reprocessing job queued (Job ID: {job_token})", "info")

    return redirect(url_for("screenings.screening_detail", encounter_id=encounter_id))


@bp.route("/delete/<int:encounter_id>", methods=["POST"])
@roles_required("admin", "data_manager")
def delete_encounter(encounter_id: int):
    """Delete an entire encounter including all associated data."""
    with get_db_session() as db:
        # Get the encounter with all related data
        encounter = db.query(PatientEncounters).filter(PatientEncounters.id == encounter_id).first()
        if not encounter:
            flash("Encounter not found", "danger")
            return redirect(url_for("screenings.list_screenings"))

        # Check permissions
        allowed_lab_unit_ids = get_user_lab_unit_ids(current_user.id)
        is_admin_like = current_user.has_role("admin")

        if not is_admin_like and encounter.lab_unit_id and allowed_lab_unit_ids and encounter.lab_unit_id not in allowed_lab_unit_ids:
            abort(403)

        # Check if there are any non-pending grading tasks for this encounter's images
        from models import GradingTask

        # Get all encounter file IDs for this encounter
        encounter_file_ids = [ef.id for ef in encounter.encounter_files] if encounter.encounter_files else []

        if encounter_file_ids:
            # Check for any non-pending grading tasks for these images
            non_pending_tasks = db.query(GradingTask).filter(
                GradingTask.encounter_file_id.in_(encounter_file_ids),
                GradingTask.state != 'pending'
            ).all()

            if non_pending_tasks:
                # Build error message with details
                task_details = []
                for task in non_pending_tasks:
                    task_details.append(f"Image ID {task.encounter_file_id} has task in '{task.state}' state")

                flash(
                    f"Cannot delete screening: {len(non_pending_tasks)} grading task(s) are not in pending state. "
                    f"{' '.join(task_details)}",
                    "danger"
                )
                return redirect(url_for("screenings.screening_detail", encounter_id=encounter_id))

        # Store patient info for flash message
        patient_id = encounter.patient_id
        patient_name = encounter.name

        # Get the ZIP file record once for reuse
        zip_file = None
        if encounter.zip_file_id:
            zip_file = db.query(ZipFile).filter(ZipFile.id == encounter.zip_file_id).first()

        # Delete all associated data (cascade delete should handle most of this)
        # But we'll be explicit for clarity and to ensure files are cleaned up

        # Delete encounter files (images and PDFs)
        from models import EncounterFile, EncounterFilePDF
        import os

        # Delete image files from disk
        image_files = db.query(EncounterFile).filter(EncounterFile.patient_encounter_id == encounter_id).all()
        for img_file in image_files:
            try:
                # Use the already queried zip_file
                if zip_file:
                    upload_date_str = zip_file.upload_date.strftime("%Y_%m_%d") if zip_file.upload_date else ""
                    from models import IMAGE_DIR
                    from utils.image_processing import get_thumbnail_filename

                    # Delete original image
                    img_path = IMAGE_DIR / upload_date_str / img_file.filename
                    if img_path.exists():
                        os.remove(img_path)
                        current_app.logger.info(
                            "Deleted image file: %s",
                            sanitize_log_value(img_file.filename),
                        )

                    # Delete thumbnail file
                    thumb_filename = get_thumbnail_filename(img_file.filename)
                    thumb_path = IMAGE_DIR / upload_date_str / thumb_filename
                    if thumb_path.exists():
                        os.remove(thumb_path)
                        current_app.logger.info(
                            "Deleted thumbnail file: %s",
                            sanitize_log_value(thumb_filename),
                        )

            except Exception as e:
                current_app.logger.warning(
                    "Failed to delete image file %s: %s",
                    sanitize_log_value(img_file.filename),
                    sanitize_log_value(e),
                )

        # Delete PDF files from disk
        pdf_files = db.query(EncounterFilePDF).filter(EncounterFilePDF.patient_encounter_id == encounter_id).all()
        for pdf_file in pdf_files:
            try:
                # Use the already queried zip_file
                if zip_file:
                    upload_date_str = zip_file.upload_date.strftime("%Y_%m_%d") if zip_file.upload_date else ""
                    from models import PDF_DIR
                    pdf_path = PDF_DIR / upload_date_str / pdf_file.filename
                    if pdf_path.exists():
                        os.remove(pdf_path)
            except Exception as e:
                current_app.logger.warning(
                    "Failed to delete PDF file %s: %s",
                    sanitize_log_value(pdf_file.filename),
                    sanitize_log_value(e),
                )

        # Delete split DR and Glaucoma report files
        from models import DiabeticRetinopathyReport, GlaucomaReport, DR_PDF_DIR, GLAUCOMA_PDF_DIR

        dr_reports = db.query(DiabeticRetinopathyReport).filter(DiabeticRetinopathyReport.patient_encounter_id == encounter_id).all()
        for dr_report in dr_reports:
            if dr_report.report_file_name:
                try:
                    # Use the already queried zip_file
                    if zip_file:
                        upload_date_str = zip_file.upload_date.strftime("%Y_%m_%d") if zip_file.upload_date else ""
                        dr_pdf_path = DR_PDF_DIR / upload_date_str / dr_report.report_file_name
                        if dr_pdf_path.exists():
                            os.remove(dr_pdf_path)
                except Exception as e:
                    current_app.logger.warning(
                        "Failed to delete DR report file %s: %s",
                        sanitize_log_value(dr_report.report_file_name),
                        sanitize_log_value(e),
                    )

        gl_reports = db.query(GlaucomaReport).filter(GlaucomaReport.patient_encounter_id == encounter_id).all()
        for gl_report in gl_reports:
            if gl_report.report_file_name:
                try:
                    # Use the already queried zip_file
                    if zip_file:
                        upload_date_str = zip_file.upload_date.strftime("%Y_%m_%d") if zip_file.upload_date else ""
                        gl_pdf_path = GLAUCOMA_PDF_DIR / upload_date_str / gl_report.report_file_name
                        if gl_pdf_path.exists():
                            os.remove(gl_pdf_path)
                except Exception as e:
                    current_app.logger.warning(
                        "Failed to delete Glaucoma report file %s: %s",
                        sanitize_log_value(gl_report.report_file_name),
                        sanitize_log_value(e),
                    )

        # Delete all pending grading tasks for this encounter's images
        if encounter_file_ids:
            pending_tasks = db.query(GradingTask).filter(
                GradingTask.encounter_file_id.in_(encounter_file_ids),
                GradingTask.state == 'pending'
            ).all()

            for task in pending_tasks:
                db.delete(task)
                current_app.logger.info(
                    "Deleted pending grading task %s for image %s",
                    sanitize_log_value(task.id),
                    sanitize_log_value(task.encounter_file_id),
                )

        # Delete the encounter (cascade will handle related database records)
        db.delete(encounter)

        # Also delete the ZIP file record and actual file to allow re-uploading the same ZIP
        if zip_file:
            # Delete the actual ZIP file from disk
            try:
                from models import PROCESSED_DIR
                # ZIP files are stored in date subdirectories under PROCESSED_DIR
                upload_date_str = zip_file.upload_date.strftime("%Y_%m_%d") if zip_file.upload_date else ""
                zip_file_path = PROCESSED_DIR / upload_date_str / zip_file.zip_filename

                if zip_file_path.exists():
                    os.remove(zip_file_path)
                    current_app.logger.info(
                        "Deleted ZIP file: %s",
                        sanitize_log_value(zip_file.zip_filename),
                    )
                else:
                    current_app.logger.warning(
                        "ZIP file not found for deletion: %s",
                        sanitize_log_value(zip_file_path),
                    )
            except Exception as e:
                current_app.logger.error(
                    "Failed to delete ZIP file %s: %s",
                    sanitize_log_value(zip_file.zip_filename),
                    sanitize_log_value(e),
                )

            # Delete the database record
            db.delete(zip_file)

        db.commit()

        flash(f"Successfully deleted screening for Patient ID: {patient_id} ({patient_name or 'Unknown'})", "success")

    return redirect(url_for("screenings.list_screenings"))


@bp.route("/delete_reports/<int:encounter_id>", methods=["POST"])
@roles_required("admin", "data_manager")
def delete_reports(encounter_id: int):
    """Delete existing DR and Glaucoma reports for an encounter."""
    with get_db_session() as db:
        # Get the encounter
        encounter = db.query(PatientEncounters).filter(PatientEncounters.id == encounter_id).first()
        if not encounter:
            flash("Encounter not found", "danger")
            return redirect(url_for("screenings.list_screenings"))

        allowed_lab_unit_ids = get_user_lab_unit_ids(current_user.id)
        # Check permissions - similar to other routes
        if encounter.lab_unit_id and allowed_lab_unit_ids and encounter.lab_unit_id not in allowed_lab_unit_ids:
             abort(403)

        # Delete existing reports
        dr_reports = db.query(DiabeticRetinopathyReport).filter_by(
            patient_encounter_id=encounter_id
        ).all()

        gl_reports = db.query(GlaucomaReport).filter_by(
            patient_encounter_id=encounter_id
        ).all()

        deleted_count = len(dr_reports) + len(gl_reports)

        # Delete all reports
        for report in dr_reports:
            db.delete(report)
        for report in gl_reports:
            db.delete(report)

        if deleted_count > 0:
            db.commit()
            flash(f"Deleted {deleted_count} report(s) for patient {encounter.patient_id}", "success")
        else:
            flash("No reports found to delete", "info")

    return redirect(url_for("screenings.screening_detail", encounter_id=encounter_id))
