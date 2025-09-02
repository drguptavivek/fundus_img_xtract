# preprocess/anonymize_images.py
# Uses ONLY existing UUIDs from DirectImageUpload. No @with_session.
# Explicit Session() lifecycle per route.

import os
from uuid import UUID

from flask import render_template, redirect, url_for, flash, current_app, jsonify, request
from flask_login import current_user
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from preprocess import bp
from auth.roles import roles_required
from direct_uploads.paths import abs_from_parts
from models import Session, User, DirectImageUpload, DirectImageVerify


# ---------------------------
# Helpers
# ---------------------------

def _uuid_str(u: UUID | str) -> str:
    """Return string form regardless of whether path converter gave UUID or str."""
    return str(u)


def _get_next_anonymize_image_uuid(db_session, current_image_id: int | None = None) -> str | None:
    """
    Returns an EXISTING UUID from DirectImageUpload, never generates one.
    Priority: unverified first, then oldest first.
    Applies lab_unit-based access restriction for non-admin/data_manager users.
    """
    # Rehydrate user + lab_units inside this session to avoid DetachedInstanceError
    user = db_session.execute(
        select(User).options(selectinload(User.lab_units)).where(User.id == current_user.id)
    ).scalar_one()

    base = (
        select(DirectImageUpload.uuid)          # Select ONLY the existing UUID
        .outerjoin(DirectImageVerify)
        .order_by(
            DirectImageVerify.id.is_(None).desc(),   # Unverified first
            DirectImageUpload.created_at.asc(),      # Oldest first (change if you prefer newest)
        )
    )

    # Restrict for non-admin/data_manager
    is_admin = current_user.has_role('admin')
    is_dm = current_user.has_role('data_manager')
    if not (is_admin or is_dm):
        allowed_lab_unit_ids = [lu.id for lu in (user.lab_units or [])]
        if not allowed_lab_unit_ids:
            return None
        base = base.where(DirectImageUpload.lab_unit_id.in_(allowed_lab_unit_ids))

    if current_image_id:
        next_uuid = db_session.execute(
            base.where(DirectImageUpload.id > current_image_id).limit(1)
        ).scalar_one_or_none()
        if next_uuid:
            return next_uuid  # already an existing DB value

    first_uuid = db_session.execute(base.limit(1)).scalar_one_or_none()
    return first_uuid


# ---------------------------
# Dashboard
# ---------------------------

@bp.route("/dashboard", methods=["GET"])
@roles_required('contributor', 'data_manager', 'admin')
def anonymization_dashboard():
    """
    Totals, recents, and a 'next image' UUID for anonymization.
    """
    db_session = Session()
    try:
        total_anonymized_images = db_session.execute(
            select(func.count(DirectImageVerify.id))
            .where(DirectImageVerify.verified_status == 'verified')
        ).scalar_one()

        pending_anonymization_images = db_session.execute(
            select(func.count(DirectImageUpload.id))
            .outerjoin(DirectImageVerify)
            .where(DirectImageVerify.id.is_(None))
        ).scalar_one()

        # Prefer FK id field for the verifier; rename if your model uses a different column
        user_verified_images = db_session.execute(
            select(func.count(DirectImageVerify.id)).where(
                DirectImageVerify.verified_status == 'verified',
                DirectImageVerify.verified_by_id == current_user.id
            )
        ).scalar_one()

        recent_verifications = db_session.execute(
            select(DirectImageVerify)
            .order_by(DirectImageVerify.verified_at.desc())
            .limit(10)
        ).scalars().all()

        next_image_uuid = _get_next_anonymize_image_uuid(db_session)

        return render_template(
            "preprocess/anonymization_dashboard.html",
            total_anonymized_images=total_anonymized_images,
            pending_anonymization_images=pending_anonymization_images,
            user_verified_images=user_verified_images,
            recent_verifications=recent_verifications,
            next_image_uuid=next_image_uuid
        )
    finally:
        db_session.close()


# ---------------------------
# Anonymize One Image
# ---------------------------

@bp.route("/anonymize_image/<uuid:uuid>", methods=["GET", "POST"])
@roles_required('contributor', 'data_manager', 'admin')
def anonymize_image(uuid: UUID):
    db_session = Session()
    try:
        # Lookup by existing UUID (DO NOT generate)
        uuid_val = _uuid_str(uuid)

        upload = db_session.execute(
            select(DirectImageUpload).filter_by(uuid=uuid_val)
        ).scalar_one_or_none()

        if not upload:
            current_app.logger.warning("Anonymize image: Upload with UUID %s not found.", uuid_val)
            flash("Image not found.", "danger")
            return redirect(url_for("preprocess.anonymization_dashboard"))

        # Access control
        is_admin = current_user.has_role('admin')
        is_dm = current_user.has_role('data_manager')
        if not (is_admin or is_dm):
            # Load user's lab_units in-session
            user = db_session.execute(
                select(User).options(selectinload(User.lab_units)).where(User.id == current_user.id)
            ).scalar_one()
            allowed = {lu.id for lu in (user.lab_units or [])}
            if upload.lab_unit_id not in allowed:
                flash("You do not have permission to anonymize this image.", "danger")
                return redirect(url_for("preprocess.anonymization_dashboard"))

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

        current_verification = db_session.execute(
            select(DirectImageVerify).filter_by(image_upload_id=upload.id)
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
                db_session.add(DirectImageVerify(
                    image_upload_id=upload.id,
                    verified_status=verified_status,
                    remarks=remarks,
                    verified_by_id=current_user.id,
                    verified_at=func.now(),
                ))
            db_session.commit()

            flash(f"Image {upload.filename} marked as {verified_status}. Redirecting...", "success")

            # Move to the next AVAILABLE existing UUID (if any)
            next_uuid = _get_next_anonymize_image_uuid(db_session, current_image_id=upload.id)
            if next_uuid:
                return redirect(url_for("preprocess.anonymize_image", uuid=next_uuid))

            flash("No more images to anonymize.", "info")
            return redirect(url_for("preprocess.anonymization_dashboard"))

        return render_template(
            "preprocess/anonymize_image.html",
            upload=upload,
            image_url=image_url,
            edited_image_url=edited_image_url,
            current_verification=current_verification,
            uuid=uuid_val,
            has_edited_version=bool(upload.has_edited and upload.edited_filename),
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

        # >>> KEY FIX: point to the 'edited' subfolder <<<
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

        db_session.commit()
        flash("Original image restored successfully!", "success")
        return jsonify({"redirect_url": url_for("preprocess.anonymize_image", uuid=uuid_val)})

    finally:
        db_session.close()