# preprocess/anonymize_images.py
# Uses ONLY existing UUIDs from DirectImageUpload. No @with_session.
# Explicit Session() lifecycle per route.

import os
from uuid import UUID
import logging

from flask import render_template, redirect, url_for, flash, current_app, jsonify, request
from flask_login import current_user
from sqlalchemy import select, func, exists, and_, select
from sqlalchemy.orm import selectinload
from sqlalchemy import case
from sqlalchemy import func
from sqlalchemy.orm import aliased

from math import ceil
from preprocess import bp
from auth.roles import roles_required
from direct_uploads.paths import abs_from_parts
from models import (
    Session, User, DirectImageUpload, DirectImageVerify, Hospital, LabUnit, Camera, Disease, Area
)

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

def _base_candidate_query(require_unverified: bool, db_session, restrict_to_user: bool):
    base = select(
        DirectImageUpload.id.label("du_id"),
        DirectImageUpload.uuid.label("du_uuid"),
        DirectImageUpload.created_at.label("du_created_at"),
    ).select_from(DirectImageUpload)

    if require_unverified:
        verified_exists = exists(
            select(1).select_from(DirectImageVerify).where(
                and_(
                    DirectImageVerify.image_upload_id == DirectImageUpload.id,
                    DirectImageVerify.verified_status == 'verified',
                )
            )
        )
        base = base.where(~verified_exists)  # keep rows with NO verified record

    # Restrict for non-admin/data_manager users by lab_units
    is_admin = current_user.has_role("admin")
    is_dm = current_user.has_role("data_manager")
    if restrict_to_user and not (is_admin or is_dm):
        user = _user_with_lab_units(db_session)
        allowed_lab_unit_ids = [lu.id for lu in (user.lab_units or [])]
        if not allowed_lab_unit_ids:
            base = base.where(False)
        else:
            base = base.where(DirectImageUpload.lab_unit_id.in_(allowed_lab_unit_ids))

    return base

def _get_next_unverified_uuid(db_session) -> str | None:
    """
    Return the UUID of the next unverified image the CURRENT USER can access (oldest first).
    If none remain, return None.
    """
    from sqlalchemy import exists, and_, select

    # Base: uploads with NO 'verified' record
    stmt = select(DirectImageUpload.uuid).where(
        ~exists(
            select(1)
            .select_from(DirectImageVerify)
            .where(
                and_(
                    DirectImageVerify.image_upload_id == DirectImageUpload.id,
                    DirectImageVerify.verified_status == 'verified'
                )
            )
        )
    )

    # Restrict for non-admin/data_manager users by their lab_units
    is_admin = current_user.has_role("admin")
    is_dm = current_user.has_role("data_manager")
    if not (is_admin or is_dm):
        user = _user_with_lab_units(db_session)
        allowed_lab_unit_ids = [lu.id for lu in (user.lab_units or [])]
        if not allowed_lab_unit_ids:
            return None
        stmt = stmt.where(DirectImageUpload.lab_unit_id.in_(allowed_lab_unit_ids))

    stmt = stmt.order_by(DirectImageUpload.created_at.asc(), DirectImageUpload.id.asc()).limit(1)
    return db_session.execute(stmt).scalars().first()

# ---------------------------
# Dashboard
# ---------------------------

@bp.route("/dashboard", methods=["GET"])
@roles_required("contributor", "data_manager", "admin")
def anonymization_dashboard():
    """
    Totals, recents, and a 'next image' UUID for anonymization.
    Supports filtering and pagination for recent verifications.
    """
    db_session = Session()
    try:
        # --- KPIs (unchanged) ---
        total_anonymized_images = db_session.execute(
            select(func.count(DirectImageVerify.id)).where(DirectImageVerify.verified_status == "verified")
        ).scalar_one()

        pending_anonymization_images = db_session.execute(
            select(func.count(DirectImageUpload.id)).where(
                ~exists(select(1).where(DirectImageVerify.image_upload_id == DirectImageUpload.id))
            )
        ).scalar_one()

        user_verified_images = db_session.execute(
            select(func.count(DirectImageVerify.id)).where(
                DirectImageVerify.verified_status == "verified",
                DirectImageVerify.verified_by_id == current_user.id,
            )
        ).scalar_one()

        # --- Filters ---
        page = request.args.get('page', 1, type=int)
        per_page = 20  # or from config
        
        f_hospital_id = request.args.get('hospital_id', '', type=str)
        f_lab_unit_id = request.args.get('lab_unit_id', '', type=str)
        f_camera_id = request.args.get('camera_id', '', type=str)
        f_disease_id = request.args.get('disease_id', '', type=str)
        f_area_id = request.args.get('area_id', '', type=str)
        f_status = request.args.get('status', '', type=str)
        f_verified_by_id = request.args.get('verified_by_id', '', type=str)
        f_filename = request.args.get('filename', '', type=str)

        # --- Data for filter dropdowns ---
        hospitals = db_session.execute(select(Hospital).order_by(Hospital.name)).scalars().all()
        lab_units = db_session.execute(select(LabUnit).order_by(LabUnit.name)).scalars().all()
        cameras = db_session.execute(select(Camera).order_by(Camera.name)).scalars().all()
        diseases = db_session.execute(select(Disease).order_by(Disease.name)).scalars().all()
        areas = db_session.execute(select(Area).order_by(Area.name)).scalars().all()
        users = db_session.execute(select(User).order_by(User.username)).scalars().all()
        
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

        next_uuid = _get_next_unverified_uuid(db_session)

        return render_template(
            "preprocess/anonymization_dashboard.html",
            total_anonymized_images=total_anonymized_images,
            pending_anonymization_images=pending_anonymization_images,
            user_verified_images=user_verified_images,
            recent_verifications=verifications,
            next_unverified_uuid=next_uuid,
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
            filters={
                'hospital_id': f_hospital_id,
                'lab_unit_id': f_lab_unit_id,
                'camera_id': f_camera_id,
                'disease_id': f_disease_id,
                'area_id': f_area_id,
                'status': f_status,
                'verified_by_id': f_verified_by_id,
                'filename': f_filename,
            }
        )
    except Exception as e:
        current_app.logger.exception("Error loading anonymization dashboard: %s", e)
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
@roles_required("contributor", "data_manager", "admin")
def anonymize_image(uuid: UUID):
    db_session = Session()
    try:
        uuid_val = _uuid_str(uuid)

        # Load the image by UUID
        upload = db_session.execute(
            select(DirectImageUpload).where(DirectImageUpload.uuid == uuid_val)
        ).scalar_one_or_none()

        if not upload:
            current_app.logger.warning("Anonymize image: Upload with UUID %s not found.", uuid_val)
            flash("Image not found.", "danger")
            return redirect(url_for("preprocess.anonymization_dashboard"))

        # Access control (lab_units) for non-admin/data_manager
        is_admin = current_user.has_role("admin")
        is_dm = current_user.has_role("data_manager")
        if not (is_admin or is_dm):
            user = _user_with_lab_units(db_session)
            allowed = {lu.id for lu in (user.lab_units or [])}
            if upload.lab_unit_id not in allowed:
                flash("You do not have permission to anonymize this image.", "danger")
                return redirect(url_for("preprocess.anonymization_dashboard"))

        # Build URLs for media endpoints (prefer edited if present for display)
        image_url = url_for(
            "media.serve_img_by_uuid_preferring_edited",
            uuid_str=str(upload.uuid),
            _external=False,
        )

        edited_image_url = None
        if upload.has_edited and upload.edited_filename:
            edited_image_url = url_for(
                "media.serve_img_by_uuid_preferring_edited",
                uuid_str=str(upload.uuid),
                _external=False,
            )

        # Current verification (if any)
        current_verification = db_session.execute(
            select(DirectImageVerify).where(DirectImageVerify.image_upload_id == upload.id)
        ).scalar_one_or_none()

        if request.method == "POST":
            verified_status = request.form.get("verified_status")
            remarks = request.form.get("remarks")

            if not verified_status:
                flash("Verification status is required.", "danger")
                return redirect(url_for("preprocess.anonymize_image", uuid=uuid_val))

            if current_verification:
                current_verification.verified_status = verified_status
                current_verification.remarks = remarks
                current_verification.verified_by_id = current_user.id
                current_verification.verified_at = func.now()
            else:
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
                db_session.commit()
                flash(f"Image {upload.filename} marked as {verified_status}.", "success")

                # After saving, go to the next UNVERIFIED (oldest). If none, stop on dashboard.
                next_uuid = _get_next_unverified_uuid(db_session)
                if next_uuid:
                    return redirect(url_for("preprocess.anonymize_image", uuid=next_uuid))

                flash("No more images to anonymize.", "info")
                return redirect(url_for("preprocess.anonymization_dashboard"))

            except Exception as e:
                current_app.logger.exception(
                    "Failed to update verification status for image UUID %s: %s", uuid_val, e
                )
                db_session.rollback()
                flash("Failed to save verification status due to a database error.", "danger")
                return redirect(url_for("preprocess.anonymize_image", uuid=uuid_val))

        # GET: If this image is already verified, show a banner and offer "next unverified" if any
        is_verified = (
            db_session.execute(
                select(DirectImageVerify.id)
                .where(DirectImageVerify.image_upload_id == upload.id, DirectImageVerify.verified_status == 'verified'))
                .scalar_one_or_none() is not None
        )
        next_unverified_uuid = _get_next_unverified_uuid(db_session)

        return render_template(
            "preprocess/anonymize_image.html",
            upload=upload,
            image_url=image_url,
            edited_image_url=edited_image_url,
            current_verification=current_verification,
            uuid=uuid_val,
            has_edited_version=bool(upload.has_edited and upload.edited_filename),
            is_verified=is_verified,
            next_unverified_uuid=next_unverified_uuid,
        )

    finally:
        db_session.close()

# ---------------------------
# Restore Original
# ---------------------------
@bp.route("/anonymize_image/<uuid:uuid>/restore_original", methods=["POST"])
@roles_required('contributor', 'data_manager', 'admin')
def restore_original_anonymized_image(uuid: UUID):
    db_session = Session()
    try:
        uuid_val = str(uuid)

        upload = db_session.execute(
            select(DirectImageUpload).where(DirectImageUpload.uuid == uuid_val)
        ).scalar_one_or_none()

        if not upload:
            return jsonify({"error": "Image not found"}), 404

        # Access control
        is_admin = current_user.has_role('admin')
        is_dm = current_user.has_role('data_manager')
        if not (is_admin or is_dm):
            user = db_session.execute(
                select(User).options(selectinload(User.lab_units)).where(User.id == current_user.id)
            ).scalar_one()
            allowed = {lu.id for lu in (user.lab_units or [])}
            if upload.lab_unit_id not in allowed:
                return jsonify({"error": "You do not have permission to restore this image."}), 403

        # Must have an edited file recorded
        if not (upload.edited_filename and upload.edited_filename.strip()):
            return jsonify({"error": "No edited version to restore."}), 400

        edited_file_path = abs_from_parts(upload.folder_rel, upload.edited_filename, "edited")
        current_app.logger.info("Deleting edited file for restore: %s", edited_file_path)

        try:
            # Delete from disk FIRST
            edited_file_path.unlink()  # raises if not found
        except FileNotFoundError:
            current_app.logger.warning("Edited file already missing: %s", edited_file_path)
            # proceed to clear DB anyway
        except Exception as e:
            current_app.logger.exception("Failed to remove edited file %s: %s", edited_file_path, e)
            db_session.rollback()
            return jsonify({"error": "Failed to delete edited file. Original not restored."}), 500

        # Now update DB to reflect original restored
        upload.edited_filename = None
        # If you also store a boolean column, uncomment:
        # upload.has_edited = False

        try:
            db_session.commit()
            flash("Original image restored successfully!", "success")
            return jsonify({"redirect_url": url_for("preprocess.anonymize_image", uuid=uuid_val)})
        except Exception as e:
            current_app.logger.exception("Failed to update database after deleting edited file for UUID %s: %s", uuid_val, e)
            db_session.rollback()
            return jsonify({"error": "Failed to update database. Original not restored."}), 500

    finally:
        db_session.close()