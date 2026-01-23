# preprocess/anonymize_images.py
# Uses ONLY existing UUIDs from DirectImageUpload. No @with_session.
# Explicit Session() lifecycle per route.

import os
from uuid import UUID
import logging

from flask import render_template, redirect, url_for, flash, current_app, jsonify, request, session
from flask_login import current_user
from sqlalchemy import select, func, exists, and_
from sqlalchemy.orm import selectinload

from math import ceil
from preprocess import bp
from auth.roles import roles_required
from utils.fileUtils import abs_from_parts
from utils.upload_eligibility import get_user_lab_unit_ids_no_admin_override
from utils.log_sanitize import sanitize_log_value
from utils.sensitive_operations import _log_sensitive_operation
from auth.utils import utcnow


editing_logger = logging.getLogger("editing")
from utils.stack_trace_handler import StackTraceContextManager, stack_trace_context, log_current_stack
from models import (
    Session,
    User,
    DirectImageUpload,
    DirectImageVerify,
    Hospital,
    LabUnit,
    Camera,
    Disease,
    Area,
    GradingTask,
    ImagePiiVerification,
)

# Import task creation services
from services.taskCreationServices import ensure_task

# ---------------------------
# Helpers
# ---------------------------

def _uuid_str(u: UUID | str) -> str:
    """Return string form regardless of whether path converter gave UUID or str."""
    return str(u)

def _user_with_lab_units(db_session) -> User:
    """Load the current user with lab_units within THIS db_session."""
    return db_session.execute(
        select(User)
        .options(selectinload(User.lab_units))
        .where(User.id == current_user.id)
    ).scalar_one()


def _normalize_task_state(state) -> str:
    if state is None:
        return ""
    if not isinstance(state, str):
        return str(state).strip().lower()
    return state.strip().lower()

def _allowed_lab_and_hospital_ids(db_session) -> tuple[set[int], set[int]]:
    """Return allowed lab units (no admin override) and their hospital ids."""
    allowed_lab_unit_ids = set(get_user_lab_unit_ids_no_admin_override(current_user.id) or [])
    if not allowed_lab_unit_ids:
        return set(), set()
    allowed_hospital_ids = {
        hospital_id
        for hospital_id, in db_session.execute(
            select(LabUnit.hospital_id).where(LabUnit.id.in_(allowed_lab_unit_ids))
        )
        if hospital_id is not None
    }
    return allowed_lab_unit_ids, allowed_hospital_ids

def _base_candidate_query(require_unverified: bool, db_session, restrict_to_user: bool, allowed_lab_unit_ids: set[int] | None = None):
    allowed_lab_unit_ids = set(allowed_lab_unit_ids or get_user_lab_unit_ids_no_admin_override(current_user.id) or [])
    base = select(
        DirectImageUpload.id.label("du_id"),
        DirectImageUpload.uuid.label("du_uuid"),
        DirectImageUpload.created_at.label("du_created_at"),
    ).select_from(DirectImageUpload)

    if require_unverified:
        # Find all image_upload_ids that are verified
        verified_subquery = (
            select(DirectImageVerify.image_upload_id)
            .where(DirectImageVerify.verified_status == 'verified')
            .distinct()
        ).subquery()
        
        # Keep rows that are NOT in the verified status
        base = base.where(
            ~DirectImageUpload.id.in_(select(verified_subquery.c.image_upload_id).scalar_subquery())
        )

    if restrict_to_user or allowed_lab_unit_ids:
        if not allowed_lab_unit_ids:
            base = base.where(False)
        else:
            base = base.where(DirectImageUpload.lab_unit_id.in_(allowed_lab_unit_ids))

    return base

def _get_next_unverified_uuid(db_session, allowed_lab_unit_ids: set[int] | None = None) -> str | None:
    """
    Return the UUID of the next unverified image the CURRENT USER can access (oldest first).
    If none remain, return None.
    """
    from sqlalchemy import exists, and_, select
    allowed_lab_unit_ids = set(allowed_lab_unit_ids or get_user_lab_unit_ids_no_admin_override(current_user.id) or [])
    if not allowed_lab_unit_ids:
        return None

    # Subquery to find all image_upload_ids that are verified
    verified_subquery = (
        select(DirectImageVerify.image_upload_id)
        .where(DirectImageVerify.verified_status == 'verified')
        .distinct()
    ).subquery()

    # Base: uploads that are NOT in the 'verified' status
    stmt = select(DirectImageUpload.uuid).where(
        ~DirectImageUpload.id.in_(select(verified_subquery.c.image_upload_id).scalar_subquery())
    )

    stmt = stmt.where(DirectImageUpload.lab_unit_id.in_(allowed_lab_unit_ids))

    stmt = stmt.order_by(DirectImageUpload.created_at.asc(), DirectImageUpload.id.asc()).limit(1)
    return db_session.execute(stmt).scalars().first()

# ---------------------------
# Dashboard
# ---------------------------

@bp.route("/dashboard", methods=["GET"])
@roles_required("admin", "local_admin", "fileUploader", "optometrist", "data_manager")
def anonymization_dashboard():
    """
    Totals, recents, and a 'next image' UUID for anonymization.
    Supports filtering and pagination for recent verifications.
    """
    db_session = Session()
    try:
        allowed_lab_unit_ids, allowed_hospital_ids = _allowed_lab_and_hospital_ids(db_session)
        if not allowed_lab_unit_ids:
            flash("No lab unit access.", "warning")
            return redirect(url_for("home.index"))

        # --- KPIs (fixed to properly handle verified/unverified transitions) ---
        # Count all records with verified_status = "verified"
        total_anonymized_images = db_session.execute(
            select(func.count(DirectImageVerify.id))
            .join(DirectImageUpload, DirectImageUpload.id == DirectImageVerify.image_upload_id)
            .where(
                DirectImageVerify.verified_status == "verified",
                DirectImageUpload.lab_unit_id.in_(allowed_lab_unit_ids),
            )
        ).scalar_one()

        # Count all DirectImageUpload records that do NOT have a verified status
        # This includes images with no verification record at all, and those with non-verified statuses
        verified_subquery = (
            select(DirectImageVerify.image_upload_id)
            .where(
                DirectImageVerify.verified_status == "verified"
            )
            .distinct()
        ).subquery()

        pending_anonymization_images = db_session.execute(
            select(func.count(DirectImageUpload.id)).where(
                DirectImageUpload.lab_unit_id.in_(allowed_lab_unit_ids),
                ~DirectImageUpload.id.in_(select(verified_subquery.c.image_upload_id).scalar_subquery())
            )
        ).scalar_one()

        # Count all verified records by the current user
        user_verified_images = db_session.execute(
            select(func.count(DirectImageVerify.id))
            .join(DirectImageUpload, DirectImageVerify.image_upload_id == DirectImageUpload.id)
            .where(
                DirectImageVerify.verified_status == "verified",
                DirectImageVerify.verified_by_id == current_user.id,
                DirectImageUpload.lab_unit_id.in_(allowed_lab_unit_ids),
            )
        ).scalar_one()

        # --- Filters ---
        page = request.args.get('page', 1, type=int)
        per_page = 20  # or from config
        
        f_hospital_id = request.args.get('hospital_id', default=None, type=int)
        f_lab_unit_id = request.args.get('lab_unit_id', default=None, type=int)
        f_camera_id = request.args.get('camera_id', default=None, type=int)
        f_disease_id = request.args.get('disease_id', default=None, type=int)
        f_area_id = request.args.get('area_id', default=None, type=int)
        f_status = request.args.get('status', '', type=str)
        f_verified_by_id = request.args.get('verified_by_id', default=None, type=int)
        f_filename = request.args.get('filename', '', type=str)

        if f_hospital_id and f_hospital_id not in allowed_hospital_ids:
            flash("Invalid hospital filter.", "danger")
            return redirect(url_for("preprocess.anonymization_dashboard"))

        if f_lab_unit_id and f_lab_unit_id not in allowed_lab_unit_ids:
            flash("Invalid lab unit filter.", "danger")
            return redirect(url_for("preprocess.anonymization_dashboard"))

        # --- Data for filter dropdowns ---
        hospitals = db_session.execute(
            select(Hospital)
            .join(LabUnit, LabUnit.hospital_id == Hospital.id)
            .where(LabUnit.id.in_(allowed_lab_unit_ids))
            .distinct()
            .order_by(Hospital.name)
        ).scalars().all()
        lab_units = db_session.execute(
            select(LabUnit)
            .where(LabUnit.id.in_(allowed_lab_unit_ids))
            .order_by(LabUnit.name)
        ).scalars().all()
        cameras = db_session.execute(
            select(Camera)
            .join(DirectImageUpload, DirectImageUpload.camera_id == Camera.id)
            .where(DirectImageUpload.lab_unit_id.in_(allowed_lab_unit_ids))
            .distinct()
            .order_by(Camera.name)
        ).scalars().all()
        diseases = db_session.execute(
            select(Disease)
            .join(DirectImageUpload, DirectImageUpload.disease_id == Disease.id)
            .where(DirectImageUpload.lab_unit_id.in_(allowed_lab_unit_ids))
            .distinct()
            .order_by(Disease.name)
        ).scalars().all()
        areas = db_session.execute(
            select(Area)
            .join(DirectImageUpload, DirectImageUpload.area_id == Area.id)
            .where(DirectImageUpload.lab_unit_id.in_(allowed_lab_unit_ids))
            .distinct()
            .order_by(Area.name)
        ).scalars().all()
        users = db_session.execute(
            select(User)
            .join(User.lab_units)
            .where(LabUnit.id.in_(allowed_lab_unit_ids))
            .distinct()
            .order_by(User.username)
        ).scalars().all()
        
        # --- Build Query for Recent Verifications ---
        query = (
            select(DirectImageVerify)
            .join(DirectImageVerify.image_upload)
            .options(
                selectinload(DirectImageVerify.image_upload).selectinload(DirectImageUpload.hospital),
                selectinload(DirectImageVerify.image_upload).selectinload(DirectImageUpload.lab_unit),
                selectinload(DirectImageVerify.image_upload).selectinload(DirectImageUpload.camera),
                selectinload(DirectImageVerify.image_upload).selectinload(DirectImageUpload.disease),
                selectinload(DirectImageVerify.image_upload).selectinload(DirectImageUpload.area),
                selectinload(DirectImageVerify.verified_by)
            )
        )
        query = query.where(DirectImageUpload.lab_unit_id.in_(allowed_lab_unit_ids))

        # Apply filters
        if f_hospital_id:
            query = query.where(DirectImageUpload.hospital_id == f_hospital_id)
        if f_lab_unit_id:
            query = query.where(DirectImageUpload.lab_unit_id == f_lab_unit_id)
        if f_camera_id:
            query = query.where(DirectImageUpload.camera_id == f_camera_id)
        if f_disease_id:
            query = query.where(DirectImageUpload.disease_id == f_disease_id)
        if f_area_id:
            query = query.where(DirectImageUpload.area_id == f_area_id)
        if f_status:
            query = query.where(DirectImageVerify.verified_status == f_status)
        if f_verified_by_id:
            query = query.where(DirectImageVerify.verified_by_id == f_verified_by_id)
        if f_filename:
            query = query.where(DirectImageUpload.filename.ilike(f'%{f_filename}%'))

        # Get total count for pagination
        total_items = db_session.execute(select(func.count()).select_from(query.subquery())).scalar_one()
        total_pages = ceil(total_items / per_page)

        # Apply pagination and ordering
        verifications = db_session.execute(
            query.order_by(DirectImageVerify.verified_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        ).scalars().all()

        next_uuid = _get_next_unverified_uuid(db_session, allowed_lab_unit_ids)

        # --- Chart Data: Pending images by disease, stacked by lab unit ---
        all_diseases = db_session.execute(
            select(Disease)
            .join(DirectImageUpload, DirectImageUpload.disease_id == Disease.id)
            .where(DirectImageUpload.lab_unit_id.in_(allowed_lab_unit_ids))
            .distinct()
            .order_by(Disease.name)
        ).scalars().all()
        all_lab_units = db_session.execute(
            select(LabUnit)
            .where(LabUnit.id.in_(allowed_lab_unit_ids))
            .order_by(LabUnit.name)
        ).scalars().all()
        
        # Build chart data
        chart_data = {}
        for disease in all_diseases:
            chart_data[disease.name] = {}
            for lab_unit in all_lab_units:
                # Count pending images for this disease and lab unit
                pending_count = db_session.execute(
                    select(func.count(DirectImageUpload.id))
                    .where(
                        DirectImageUpload.disease_id == disease.id,
                        DirectImageUpload.lab_unit_id == lab_unit.id,
                        ~exists(select(1).where(
                            and_(
                                DirectImageVerify.image_upload_id == DirectImageUpload.id,
                                DirectImageVerify.verified_status == 'verified'
                            )
                        ))
                    )
                ).scalar_one()
                if pending_count > 0:
                    chart_data[disease.name][lab_unit.name] = pending_count

        filters_payload = {
            'hospital_id': str(f_hospital_id) if f_hospital_id is not None else "",
            'lab_unit_id': str(f_lab_unit_id) if f_lab_unit_id is not None else "",
            'camera_id': str(f_camera_id) if f_camera_id is not None else "",
            'disease_id': str(f_disease_id) if f_disease_id is not None else "",
            'area_id': str(f_area_id) if f_area_id is not None else "",
            'status': f_status,
            'verified_by_id': str(f_verified_by_id) if f_verified_by_id is not None else "",
            'filename': f_filename,
        }

        return render_template(
            "preprocess/anonymization_dashboard.html",
            total_anonymized_images=total_anonymized_images,
            pending_anonymization_images=pending_anonymization_images,
            user_verified_images=user_verified_images,
            recent_verifications=verifications,
            next_unverified_uuid=next_uuid,
            chart_data=chart_data,
            # Pagination
            page=page,
            per_page=per_page,
            total_pages=total_pages,
            total_items=total_items,
            # Filters data
            hospitals=hospitals,
            lab_units=lab_units,
            cameras=cameras,
            diseases=diseases,
            areas=areas,
            users=users,
            # Current filter values
            filters=filters_payload,
        )
    except Exception as e:
        editing_logger.exception("Error loading anonymization dashboard: %s", e)
        flash("Failed to load dashboard data. Please try again later.", "danger")
        return render_template(
            "preprocess/anonymization_dashboard.html",
            total_anonymized_images=0,
            pending_anonymization_images=0,
            user_verified_images=0,
            recent_verifications=[],
            next_unverified_uuid=None,
            page=1, per_page=20, total_pages=0, total_items=0,
            hospitals=[], lab_units=[], cameras=[], diseases=[], areas=[], users=[],
            filters={}
        )
    finally:
        db_session.close()

# ---------------------------
# Anonymize One Image
# ---------------------------

@bp.route("/anonymize_image/<uuid:uuid>", methods=["GET", "POST"])
@roles_required("admin", "local_admin", "fileUploader", "optometrist", "data_manager")
def anonymize_image(uuid: UUID):
    # Use stack trace context manager to capture any exceptions
    db_session = Session()
    try:
        allowed_lab_unit_ids, _ = _allowed_lab_and_hospital_ids(db_session)
        if not allowed_lab_unit_ids:
            flash("No lab unit access.", "warning")
            return redirect(url_for("home.index"))

        uuid_val = _uuid_str(uuid)

        # Log request details for debugging
        editing_logger.debug(
            "Starting anonymize_image function for UUID %s - User: %s, Method: %s",
            uuid_val,
            current_user.username if current_user else "Unknown",
            request.method
        )

        # Load the image by UUID
        upload = db_session.execute(
            select(DirectImageUpload).where(DirectImageUpload.uuid == uuid_val)
        ).scalar_one_or_none()

        if not upload:
            editing_logger.warning("Anonymize image: Upload with UUID %s not found.", uuid_val)
            flash("Image not found.", "danger")
            return redirect(url_for("preprocess.anonymization_dashboard"))

        if upload.lab_unit_id not in allowed_lab_unit_ids:
            flash("You do not have permission to anonymize this image.", "danger")
            return redirect(url_for("preprocess.anonymization_dashboard"))

        editing_locked = False
        blocking_task_states: list[str] = []
        task_state_rows = db_session.execute(
            select(GradingTask.state).where(GradingTask.direct_image_upload_id == upload.id)
        ).scalars().all()
        if task_state_rows:
            normalized_task_states = [_normalize_task_state(state) for state in task_state_rows]
            blocking_task_states = sorted({state for state in normalized_task_states if state and state != "pending"})
            editing_locked = False

        # Access control logging scoped to assigned lab units
        editing_logger.debug(
            "Access control check - User: %s, Allowed lab units: %s",
            current_user.username if current_user else "Unknown",
            sorted(allowed_lab_unit_ids),
        )
        
        editing_logger.debug(
            "User lab units - User: %s, Upload lab unit ID: %s, Allowed: %s",
            current_user.username if current_user else "Unknown",
            upload.lab_unit_id,
            upload.lab_unit_id in allowed_lab_unit_ids
        )

        session["anonymize_edit_uuid"] = uuid_val
        override_required = bool(blocking_task_states)

        # Build URLs for media endpoints (prefer edited if present for display)
        image_url = url_for(
            "media._directImgFinalByUUID",
            uuid_str=str(upload.uuid),
            _external=False,
        )

        edited_image_url = None
        if upload.edited_filename:
            from utils.fileUtils import abs_from_parts
            import os
            
            # Get the edited file path
            edited_file_path = abs_from_parts(upload.folder_rel, upload.edited_filename, "edited")
            
            # Add a timestamp parameter based on the file's modification time for cache busting
            try:
                mtime = int(os.path.getmtime(edited_file_path))
                edited_image_url = url_for(
                    "media._directImgFinalByUUID",
                    uuid_str=str(upload.uuid),
                    _external=False,
                    t=str(mtime)
                )
            except (OSError, ValueError):
                # If we can't get modification time, use current time as fallback
                import time
                edited_image_url = url_for(
                    "media._directImgFinalByUUID",
                    uuid_str=str(upload.uuid),
                    _external=False,
                    t=str(int(time.time()))
                )

        # Current verification (if any)
        current_verification = db_session.execute(
            select(DirectImageVerify).where(DirectImageVerify.image_upload_id == upload.id)
        ).scalar_one_or_none()
        
        editing_logger.debug(
            "Current verification status - Upload ID: %s, Has verification: %s, Status: %s",
            upload.id,
            current_verification is not None,
            current_verification.verified_status if current_verification else "None"
        )

        if request.method == "POST":
            # Log request details for debugging
            editing_logger.debug(
                "Processing anonymization POST request for UUID %s - User: %s, Form data: %s",
                uuid_val, 
                current_user.username if current_user else "Unknown",
                dict(request.form)
            )
            
            # Handle the toggle switch - if checked, it will be "verified", otherwise it won't be in form data
            verified_status = request.form.get("verified_status", "unverified")
            remarks = request.form.get("remarks")
            
            editing_logger.debug(
                "Form processing - Verified status: %s, Remarks: %s, Upload ID: %s",
                verified_status, remarks, upload.id if upload else "Unknown"
            )

            if current_verification:
                editing_logger.debug("Updating existing verification record for upload ID: %s", upload.id)
                current_verification.verified_status = verified_status
                current_verification.remarks = remarks
                current_verification.verified_by_id = current_user.id
                current_verification.verified_at = func.now()
            else:
                editing_logger.debug("Creating new verification record for upload ID: %s", upload.id)
                db_session.add(
                    DirectImageVerify(
                        image_upload_id=upload.id,
                        verified_status=verified_status,
                        remarks=remarks,
                        verified_by_id=current_user.id,
                        verified_at=func.now(),
                    )
                )

            try:
                # Handle task creation/removal based on verification status
                editing_logger.debug(
                    "Processing verification status '%s' for upload ID: %s (verification record already created/updated)", 
                    verified_status, upload.id
                )
                
                if verified_status == "verified":
                    # Set the verification status
                    editing_logger.debug("Handling verified status for upload ID: %s", upload.id)
                    # The verification record has already been created/updated above, so we don't need to do it again
                    # Just commit the verification first
                    editing_logger.debug("Attempting to commit verification for upload ID: %s", upload.id)
                    try:
                        db_session.commit()
                        editing_logger.debug("Successfully committed verification for upload ID: %s", upload.id)
                    except Exception as commit_error:
                        editing_logger.exception(
                            "Failed to commit verification for upload ID: %s - Error: %s", 
                            upload.id, commit_error
                        )
                        raise
                    
                    try:
                        # Create a grading task for the verified direct image
                        ensure_task(upload.uuid, upload.disease_id, db_session)
                        editing_logger.info(
                            "Created grading task for verified direct image UUID %s", upload.uuid
                        )
                    except Exception as task_error:
                        editing_logger.exception(
                            "Failed to create grading task for verified direct image UUID %s: %s", 
                            upload.uuid, task_error
                        )
                        # Don't fail the verification if task creation fails, just log it
                
                elif verified_status != "verified":
                    # If the image is being unverified, check if we can unverify
                    try:
                        from services.taskCreationServices import can_unverify_image
                        # Check if we can unverify the image (all tasks must be pending)
                        if not can_unverify_image(db_session, kind="direct", image_id=upload.id):
                            # Prevent unverification if tasks are not pending
                            flash("Cannot unverify image - some tasks are in progress.", "danger")
                            return redirect(url_for("preprocess.anonymize_image", uuid=uuid_val))
                        
                        # The verification record has already been created/updated above, so we don't need to do it again
                        # Just commit the verification
                        editing_logger.debug("Attempting to commit verification for unverified status, upload ID: %s", upload.id)
                        try:
                            db_session.commit()
                            editing_logger.debug("Successfully committed verification for unverified status, upload ID: %s", upload.id)
                        except Exception as commit_error:
                            editing_logger.exception(
                                "Failed to commit verification for unverified status, upload ID: %s - Error: %s", 
                                upload.id, commit_error
                            )
                            raise
                        
                        # Remove all pending grading tasks for this image
                        try:
                            from services.taskCreationServices import remove_pending_tasks
                            removed_count = remove_pending_tasks(db_session, kind="direct", image_id=upload.id)
                            if removed_count > 0:
                                editing_logger.info(
                                    "Removed %d pending grading task(s) for unverified direct image UUID %s", 
                                    removed_count, upload.uuid
                                )
                        except Exception as task_error:
                            editing_logger.exception(
                                "Failed to remove grading tasks for unverified direct image UUID %s: %s", 
                                upload.uuid, task_error
                            )
                            # Don't fail the unverification if task removal fails, just log it
                    
                    except Exception as task_error:
                        editing_logger.exception(
                            "Failed to check if direct image UUID %s can be unverified: %s", 
                            upload.uuid, task_error
                        )
                        flash("Failed to verify unverification conditions.", "danger")
                        return redirect(url_for("preprocess.anonymize_image", uuid=uuid_val))
                
                else:
                    # For other cases, the verification record has already been created/updated above
                    # Just commit the verification
                    editing_logger.debug("Attempting to commit verification for other status '%s', upload ID: %s", verified_status, upload.id)
                    try:
                        db_session.commit()
                        editing_logger.debug("Successfully committed verification for other status '%s', upload ID: %s", verified_status, upload.id)
                    except Exception as commit_error:
                        editing_logger.exception(
                            "Failed to commit verification for other status '%s', upload ID: %s - Error: %s", 
                            verified_status, upload.id, commit_error
                        )
                        raise
                
                flash(f"Image {upload.filename} marked as {verified_status}.", "success")

                # After saving, go to the next UNVERIFIED (oldest). If none, stop on dashboard.
                next_uuid = _get_next_unverified_uuid(db_session)
                editing_logger.debug(
                    "Redirect logic - Current upload ID: %s, Next UUID: %s", 
                    upload.id, next_uuid
                )
                
                if next_uuid:
                    editing_logger.debug("Redirecting to next unverified image: %s", next_uuid)
                    return redirect(url_for("preprocess.anonymize_image", uuid=next_uuid))

                editing_logger.debug("No more images to anonymize, redirecting to dashboard")
                flash("No more images to anonymize.", "info")
                return redirect(url_for("preprocess.anonymization_dashboard"))

            except Exception as e:
                editing_logger.exception(
                    "Failed to update verification status for image UUID %s: %s",
                    sanitize_log_value(uuid_val),
                    sanitize_log_value(e)
                )
                editing_logger.debug(
                    "Database error details - Filename: %s, Uploaded: %s, Uploader: %s, "
                    "Hospital: %s, Lab Unit: %s, Camera: %s, Disease: %s, Area: %s",
                    sanitize_log_value(upload.filename if upload else "Unknown"),
                    sanitize_log_value(upload.created_at if upload else "Unknown"),
                    sanitize_log_value(current_user.username if current_user else "Unknown"),
                    sanitize_log_value(upload.hospital.name if upload and upload.hospital else "Unknown"),
                    sanitize_log_value(upload.lab_unit.name if upload and upload.lab_unit else "Unknown"),
                    sanitize_log_value(upload.camera.name if upload and upload.camera else "Unknown"),
                    sanitize_log_value(upload.disease.name if upload and upload.disease else "Unknown"),
                    sanitize_log_value(upload.area.name if upload and upload.area else "Unknown")
                )
                editing_logger.debug("Rolling back database session")
                db_session.rollback()
                editing_logger.debug("Database session rolled back")
                flash("Failed to save verification status due to a database error.", "danger")
                return redirect(url_for("preprocess.anonymize_image", uuid=uuid_val))

        # GET: If this image is already verified, show a banner and offer "next unverified" if any
        is_verified = (
            db_session.execute(
                select(DirectImageVerify.id)
                .where(DirectImageVerify.image_upload_id == upload.id, DirectImageVerify.verified_status == 'verified'))
                .scalar_one_or_none() is not None
        )
        next_unverified_uuid = _get_next_unverified_uuid(db_session, allowed_lab_unit_ids)
        
        editing_logger.debug(
            "GET request processing - Upload ID: %s, Is verified: %s, Next unverified UUID: %s",
            upload.id,
            is_verified,
            next_unverified_uuid
        )

        return render_template(
            "preprocess/anonymize_image.html",
            upload=upload,
            image_url=image_url,
            edited_image_url=edited_image_url,
            current_verification=current_verification,
            uuid=uuid_val,
            has_edited_version=bool(upload.edited_filename),
            is_verified=is_verified,
            next_unverified_uuid=next_unverified_uuid,
            editing_locked=editing_locked,
            blocking_task_states=blocking_task_states,
            override_required=override_required,
        )

    finally:
        db_session.close()


@bp.route("/anonymize_image/<uuid:uuid>/pii_override", methods=["POST"])
@roles_required("admin", "local_admin", "fileUploader", "optometrist", "data_manager")
def pii_override(uuid: UUID):
    db_session = Session()
    try:
        allowed_lab_unit_ids, _ = _allowed_lab_and_hospital_ids(db_session)
        if not allowed_lab_unit_ids:
            flash("No lab unit access.", "warning")
            return redirect(url_for("home.index"))

        uuid_val = _uuid_str(uuid)
        upload = db_session.execute(
            select(DirectImageUpload).where(DirectImageUpload.uuid == uuid_val)
        ).scalar_one_or_none()
        if not upload:
            flash("Image not found.", "danger")
            return redirect(url_for("preprocess.anonymization_dashboard"))
        if upload.lab_unit_id not in allowed_lab_unit_ids:
            flash("You do not have permission to update PII status for this image.", "danger")
            return redirect(url_for("preprocess.anonymization_dashboard"))

        pii_status = request.form.get("pii_status")
        if pii_status not in {"clear", "detected"}:
            flash("Invalid PII status.", "danger")
            return redirect(url_for("preprocess.anonymize_image", uuid=uuid_val))

        image_variant = "edited" if upload.edited_filename else "orig"
        record = db_session.execute(
            select(ImagePiiVerification)
            .where(
                ImagePiiVerification.image_uuid == upload.uuid,
                ImagePiiVerification.image_variant == image_variant,
            )
        ).scalar_one_or_none()

        if record:
            record.pii_status = pii_status
            record.source = "manual"
            record.checked_at = utcnow()
        else:
            db_session.add(
                ImagePiiVerification(
                    image_uuid=upload.uuid,
                    image_variant=image_variant,
                    pii_status=pii_status,
                    source="manual",
                    checked_at=utcnow(),
                )
            )

        try:
            from analytics.route_dataset_curation import _clear_dataset_screen_cache

            _clear_dataset_screen_cache()
        except Exception:
            editing_logger.warning("Failed to clear dataset screen cache after PII override.")

        db_session.commit()
        flash(f"PII status set to {pii_status} (manual).", "success")
        return redirect(url_for("preprocess.anonymize_image", uuid=uuid_val))
    except Exception as exc:
        db_session.rollback()
        editing_logger.exception(
            "Failed to update PII override for uuid=%s: %s",
            sanitize_log_value(str(uuid)),
            sanitize_log_value(str(exc)),
        )
        flash("Failed to update PII override.", "danger")
        return redirect(url_for("preprocess.anonymize_image", uuid=_uuid_str(uuid)))
    finally:
        db_session.close()

# ---------------------------
# Restore Original
# ---------------------------
@bp.route("/anonymize_image/<uuid:uuid>/restore_original", methods=["POST"])
@roles_required("admin", "local_admin", "fileUploader", "optometrist", "data_manager")
def restore_original_anonymized_image(uuid: UUID):
    db_session = Session()
    try:
        allowed_lab_unit_ids, _ = _allowed_lab_and_hospital_ids(db_session)
        if not allowed_lab_unit_ids:
            return jsonify({"error": "No lab unit access."}), 403

        uuid_val = str(uuid)

        upload = db_session.execute(
            select(DirectImageUpload).where(DirectImageUpload.uuid == uuid_val)
        ).scalar_one_or_none()

        if not upload:
            return jsonify({"error": "Image not found"}), 404

        # Access control
        if upload.lab_unit_id not in allowed_lab_unit_ids:
            return jsonify({"error": "You do not have permission to restore this image."}), 403

        task_states = db_session.execute(
            select(GradingTask.state).where(GradingTask.direct_image_upload_id == upload.id)
        ).scalars().all()
        has_non_pending = any(_normalize_task_state(state) not in ("", "pending") for state in task_states)
        override_allowed = session.get("anonymize_edit_uuid") == uuid_val
        if has_non_pending and not override_allowed:
            return jsonify({"error": "Cannot restore image while grading tasks are in progress."}), 409

        # Must have an edited file recorded
        if not (upload.edited_filename and upload.edited_filename.strip()):
            return jsonify({"error": "No edited version to restore."}), 400

        edited_file_path = abs_from_parts(upload.folder_rel, upload.edited_filename, "edited")
        editing_logger.info("Deleting edited file for restore: %s", edited_file_path)

        try:
            # Delete from disk FIRST
            edited_file_path.unlink()  # raises if not found
        except FileNotFoundError:
            editing_logger.warning("Edited file already missing: %s", edited_file_path)
            # proceed to clear DB anyway
        except Exception as e:
            editing_logger.exception("Failed to remove edited file %s: %s", edited_file_path, e)
            db_session.rollback()
            return jsonify({"error": "Failed to delete edited file. Original not restored."}), 500

        # Now update DB to reflect original restored
        upload.edited_filename = None
        # If you also store a boolean column, uncomment:
        # upload.has_edited = False

        try:
            db_session.commit()
            if has_non_pending and override_allowed:
                _log_sensitive_operation(
                    operation="direct_upload_anonymize_override",
                    status="completed",
                    details={
                        "upload_id": upload.id,
                        "upload_uuid": str(upload.uuid),
                        "task_states": task_states,
                        "action": "restore_original",
                        "source": "anonymize_ui",
                    },
                )
            flash("Original image restored successfully!", "success")
            return jsonify({"redirect_url": url_for("preprocess.anonymize_image", uuid=uuid_val)})
        except Exception as e:
            editing_logger.exception("Failed to update database after deleting edited file for UUID %s: %s", uuid_val, e)
            # Log the stack trace using our stack trace handler
            from utils.stack_trace_handler import log_stack_trace
            log_stack_trace(
                message=f"Database error in restore_original_anonymized_image for UUID {uuid_val}",
                exception=e
            )
            db_session.rollback()
            return jsonify({"error": "Failed to update database. Original not restored."}), 500

    finally:
        db_session.close()
