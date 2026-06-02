from flask import render_template, abort, current_app, flash, redirect, url_for, request, jsonify
from flask_login import login_required, current_user
from auth.roles import roles_required
from sqlalchemy import or_

from models import GradingTask, PatientEncounters, EncounterSetImage, Disease
from upload_profiles.models import PatientEncounterTargetDisease
from db_transaction_manager import transaction_scope
from utils.utils import with_session
from utils.hospital_scoping import apply_scoping
from marshmallow import Schema, fields, validate, ValidationError
from . import bp


# =========================================================================
# REQUEST SCHEMAS (P1.4: Input Validation)
# =========================================================================

class CropCoordinatesSchema(Schema):
    """Validate crop coordinates for image editing"""
    x = fields.Integer(required=False, validate=validate.Range(min=0))
    y = fields.Integer(required=False, validate=validate.Range(min=0))
    width = fields.Integer(required=False, validate=validate.Range(min=1))
    height = fields.Integer(required=False, validate=validate.Range(min=1))


class SaveEditRequestSchema(Schema):
    """Validate save_edit request data"""
    crop = fields.Nested(CropCoordinatesSchema, required=False)


# =========================================================================
# UTILITY FUNCTIONS (P1.3: S3 Hospital Scoping)
# =========================================================================

def validate_s3_config_access(image, current_user, db):
    """
    Validate that user has access to image's S3 config (if used).

    P1.3: Prevents cross-hospital S3 access

    Args:
        image: EncounterSetImage model instance
        current_user: Current user
        db: Database session

    Returns:
        (is_valid, error_message) tuple
    """
    if not image.s3_config_id:
        # Image uses local storage, not S3
        return True, None

    from models import S3Config

    s3_config = db.query(S3Config).filter_by(id=image.s3_config_id).first()
    if not s3_config:
        # S3 config not found (data inconsistency)
        return False, "S3 configuration not found"

    # Verify S3 config belongs to user's hospital
    if s3_config.hospital_id != current_user.hospital_id:
        import logging
        logger = logging.getLogger("verify_encounter_set")
        logger.warning(
            "Cross-hospital S3 access attempt blocked",
            extra={
                'user_id': current_user.id,
                'user_hospital': current_user.hospital_id,
                'image_uuid': image.uuid,
                's3_hospital': s3_config.hospital_id
            }
        )
        return False, "Access denied to S3 storage"

    return True, None

@bp.route("/")
@login_required
@roles_required("admin", "optometrist", "data_manager")
def index():
    """List encounter sets pending verification."""
    with transaction_scope() as db:
        # Get encounters that are set-based and NOT yet verified
        # Apply hospital scoping to prevent cross-hospital access
        encounters = db.query(PatientEncounters).filter(
            PatientEncounters.is_set_based == True,
            or_(
                PatientEncounters.encounter_verified_status == 'pending',
                PatientEncounters.encounter_verified_status.is_(None),
            ),
        )

        # Apply hospital scoping (operation='upload' for hospital-bound)
        encounters = apply_scoping(encounters, PatientEncounters, current_user, 'upload')

        encounters = encounters.order_by(PatientEncounters.id.desc()).all()

        return render_template("verify_encounter_set/index.html", encounters=encounters)

@bp.route("/verify/<uuid>")
@login_required
@roles_required("admin", "optometrist", "data_manager")
def verify_encounter(uuid):
    """View and manage a specific encounter set for verification."""
    with transaction_scope() as db:
        # Query encounter by UUID
        query = db.query(PatientEncounters).filter_by(uuid=uuid)

        # Apply hospital scoping (operation='upload' for hospital-bound)
        query = apply_scoping(query, PatientEncounters, current_user, 'upload')

        encounter = query.first()
        if not encounter:
            abort(404)

        if not encounter.is_set_based:
            flash("This encounter is not set-based.", "warning")
            return redirect(url_for("verify_encounter_set.index"))

        # Get images in the set, ordered by spatial position
        images = db.query(EncounterSetImage).filter_by(patient_encounter_id=encounter.id).order_by(EncounterSetImage.spatial_position).all()

        # Create a 1-9 mapping
        grid = {i: None for i in range(1, 10)}
        for img in images:
            if 1 <= img.spatial_position <= 9:
                grid[img.spatial_position] = img

        return render_template("verify_encounter_set/verify.html", encounter=encounter, grid=grid)

@bp.route("/update_position", methods=["POST"])
@login_required
@roles_required("admin", "optometrist", "data_manager")
def update_position():
    """Update the spatial position of an image in an encounter set."""
    data = request.json
    image_uuid = data.get("image_uuid")
    new_position = data.get("position")
    
    if not image_uuid or new_position is None:
        return jsonify({"success": False, "message": "Missing image_uuid or position"}), 400
        
    try:
        new_position = int(new_position)
        if not (1 <= new_position <= 9):
            raise ValueError()
    except ValueError:
        return jsonify({"success": False, "message": "Invalid position"}), 400

    with transaction_scope() as db:
        img = db.query(EncounterSetImage).filter_by(uuid=image_uuid).first()
        if not img:
            return jsonify({"success": False, "message": "Image not found"}), 404

        # Verify encounter is accessible (apply hospital scoping)
        query = db.query(PatientEncounters).filter_by(id=img.patient_encounter_id)
        query = apply_scoping(query, PatientEncounters, current_user, 'upload')
        encounter = query.first()

        if not encounter:
            # Encounter not found or user doesn't have access
            return jsonify({"success": False, "message": "Image not found"}), 404

        # Check if another image already occupies this position
        existing = db.query(EncounterSetImage).filter_by(
            patient_encounter_id=img.patient_encounter_id,
            spatial_position=new_position
        ).first()

        if existing:
            # Swap positions
            existing.spatial_position = img.spatial_position

        img.spatial_position = new_position

        return jsonify({"success": True})

@bp.route("/finalize/<uuid>", methods=["POST"])
@login_required
@roles_required("admin", "optometrist", "data_manager")
def finalize_verification(uuid):
    """Mark an encounter set as verified and trigger task creation."""
    from auth.utils import utcnow
    from utils.upload_eligibility import get_user_lab_unit_ids_no_admin_override
    # Potential task creation import
    # from tasks.taskCreationServices import create_grading_task_for_encounter_set

    with transaction_scope() as db:
        # P0.5: Use row-level locking for atomic finalization
        # Lock the encounter for update (prevents concurrent modifications)
        encounter = db.query(PatientEncounters)\
            .filter_by(uuid=uuid)\
            .with_for_update()\
            .first()

        if not encounter:
            abort(404)

        # Check user has access to this encounter's lab unit
        allowed_lab_unit_ids = get_user_lab_unit_ids_no_admin_override(current_user.id)
        if encounter.lab_unit_id not in allowed_lab_unit_ids:
            flash("You don't have permission to verify this encounter set.", "danger")
            return redirect(url_for("verify_encounter_set.index"))

        # Lock all images while checking (atomic transaction)
        images = db.query(EncounterSetImage)\
            .filter_by(patient_encounter_id=encounter.id)\
            .with_for_update()\
            .all()

        # Check all images are reviewed (safe - images are locked)
        unreviewed_count = sum(1 for img in images if not img.is_reviewed)

        if unreviewed_count > 0:
            flash(f"Cannot finalize: {unreviewed_count} image(s) not yet reviewed. Please review all images before verifying.", "warning")
            return redirect(url_for("verify_encounter_set.verify_encounter", uuid=uuid))

        # Finalize (atomic - encounter and images locked until commit)
        encounter.encounter_verified_status = 'verified'
        encounter.encounter_verified_by = current_user.username
        encounter.encounter_verified_at = utcnow()

        created_tasks = _create_verified_encounter_set_tasks(db, encounter)

        task_message = f" Created {created_tasks} grading task(s)." if created_tasks else ""
        flash(f"Encounter set {encounter.name} verified successfully.{task_message}", "success")
        return redirect(url_for("verify_encounter_set.index"))


def _create_verified_encounter_set_tasks(db, encounter: PatientEncounters) -> int:
    """Create pending grading tasks for verified EncounterSet target diseases."""
    target_disease_ids = {
        row[0]
        for row in db.query(PatientEncounterTargetDisease.disease_id)
        .filter(PatientEncounterTargetDisease.patient_encounter_id == encounter.id)
        .all()
    }
    if not target_disease_ids and encounter.disease_id:
        target_disease_ids = {encounter.disease_id}

    created = 0
    for disease_id in sorted(target_disease_ids):
        existing = (
            db.query(GradingTask.id)
            .filter(
                GradingTask.patient_encounter_id == encounter.id,
                GradingTask.disease_id == disease_id,
            )
            .first()
        )
        if existing:
            continue
        db.add(
            GradingTask(
                patient_encounter_id=encounter.id,
                disease_id=disease_id,
                lab_unit_id=encounter.lab_unit_id,
                state="pending",
            )
        )
        created += 1
    if created:
        db.flush()
    return created


@bp.route("/edit/<uuid>", methods=["GET"])
@login_required
@roles_required("admin", "optometrist", "data_manager")
def edit_image(uuid):
    """Edit an encounter set image (crop/mask PII)."""
    from models import GradingTask
    from sqlalchemy import select

    with transaction_scope() as db:
        img = db.query(EncounterSetImage).filter_by(uuid=uuid).first()
        if not img:
            abort(404)

        # Query encounter and apply hospital scoping
        query = db.query(PatientEncounters).filter_by(id=img.patient_encounter_id)
        query = apply_scoping(query, PatientEncounters, current_user, 'upload')
        encounter = query.first()

        if not encounter:
            # Encounter not found or user doesn't have access
            abort(404)

        # P1.3: Validate S3 config access (defense-in-depth)
        if img.s3_config_id:
            is_valid, error_msg = validate_s3_config_access(img, current_user, db)
            if not is_valid:
                abort(403)

        # Check if grading tasks exist - block editing if they do
        task_states = db.execute(
            select(GradingTask.state).where(GradingTask.patient_encounter_id == encounter.id)
        ).scalars().all()
        active_tasks = [s for s in task_states if s and s.lower() != 'pending']
        if active_tasks:
            flash(f"Editing blocked. Grading tasks already in progress: {', '.join(set(active_tasks))}.", "danger")
            return redirect(url_for("verify_encounter_set.verify_encounter", uuid=encounter.uuid))

        # Determine which image URL to load (edited or original)
        if img.edited_filename:
            image_url = url_for("media._encounterSetImageEditedByUUID", uuid_str=img.uuid)
        else:
            image_url = url_for("media._encounterSetImageByUUID", uuid_str=img.uuid)

        return render_template(
            "verify_encounter_set/edit_image.html",
            image=img,
            encounter=encounter,
            image_url=image_url,
            has_edited_version=bool(img.edited_filename)
        )


@bp.route("/save_edit/<uuid>", methods=["POST"])
@login_required
@roles_required("admin", "optometrist", "data_manager")
def save_edit(uuid):
    """Save edited image data (crop/mask coordinates applied)."""
    from utils.fileUtils import abs_from_parts
    from PIL import Image
    import io

    # P1.4: Validate request data
    data = request.json or {}
    schema = SaveEditRequestSchema()

    try:
        validated_data = schema.load(data)
    except ValidationError as e:
        return jsonify({
            "success": False,
            "message": "Invalid request data",
            "errors": e.messages
        }), 422

    with transaction_scope() as db:
        img = db.query(EncounterSetImage).filter_by(uuid=uuid).first()
        if not img:
            return jsonify({"success": False, "message": "Image not found"}), 404

        # Query encounter and apply hospital scoping
        query = db.query(PatientEncounters).filter_by(id=img.patient_encounter_id)
        query = apply_scoping(query, PatientEncounters, current_user, 'upload')
        encounter = query.first()

        if not encounter:
            # Encounter not found or user doesn't have access
            return jsonify({"success": False, "message": "Image not found"}), 404

        # P1.1: Image editing feature not yet implemented
        # Return 501 Not Implemented with clear message to user
        return jsonify({
            "success": False,
            "message": "Image editing feature is not yet implemented",
            "details": "Image cropping and masking will be available in a future release. "
                       "Please mark the image as anonymized if PII needs to be masked."
        }), 501


@bp.route("/mark_anonymized/<uuid>", methods=["POST"])
@login_required
@roles_required("admin", "optometrist", "data_manager")
def mark_anonymized(uuid):
    """Mark an image as anonymized (PII masked)."""

    with transaction_scope() as db:
        img = db.query(EncounterSetImage).filter_by(uuid=uuid).first()
        if not img:
            return jsonify({"success": False, "message": "Image not found"}), 404

        # Query encounter and apply hospital scoping
        query = db.query(PatientEncounters).filter_by(id=img.patient_encounter_id)
        query = apply_scoping(query, PatientEncounters, current_user, 'upload')
        encounter = query.first()

        if not encounter:
            # Encounter not found or user doesn't have access
            return jsonify({"success": False, "message": "Image not found"}), 404

        # P1.3: Validate S3 config access (defense-in-depth)
        if img.s3_config_id:
            is_valid, error_msg = validate_s3_config_access(img, current_user, db)
            if not is_valid:
                return jsonify({"success": False, "message": "Permission denied"}), 403

        img.is_anonymized = True
        img.is_reviewed = True

        return jsonify({"success": True})


@bp.route("/mark_all_anonymized/<uuid>", methods=["POST"])
@login_required
@roles_required("admin", "optometrist", "data_manager")
def mark_all_anonymized(uuid):
    """Mark all images in an encounter set as anonymized."""
    from utils.upload_eligibility import get_user_lab_unit_ids_no_admin_override

    with transaction_scope() as db:
        encounter = db.query(PatientEncounters).filter_by(uuid=uuid).first()
        if not encounter:
            return jsonify({"success": False, "message": "Encounter not found"}), 404

        # Check access
        allowed_lab_unit_ids = get_user_lab_unit_ids_no_admin_override(current_user.id)
        if encounter.lab_unit_id not in allowed_lab_unit_ids:
            return jsonify({"success": False, "message": "Permission denied"}), 403

        images = db.query(EncounterSetImage).filter_by(patient_encounter_id=encounter.id).all()
        count = 0
        for img in images:
            img.is_anonymized = True
            img.is_reviewed = True
            count += 1

        return jsonify({"success": True, "count": count})


@bp.route("/restore_original/<uuid>", methods=["POST"])
@login_required
@roles_required("admin", "optometrist", "data_manager")
def restore_original(uuid):
    """Restore the original image (remove edited version)."""
    from utils.upload_eligibility import get_user_lab_unit_ids_no_admin_override
    from utils.fileUtils import abs_from_parts
    from utils.media_cache import bump_media_cache_version
    from models import GradingTask
    from sqlalchemy import select

    with transaction_scope() as db:
        img = db.query(EncounterSetImage).filter_by(uuid=uuid).first()
        if not img:
            return jsonify({"success": False, "message": "Image not found"}), 404

        encounter = db.query(PatientEncounters).filter_by(id=img.patient_encounter_id).first()
        if not encounter:
            return jsonify({"success": False, "message": "Encounter not found"}), 404

        # Check access
        allowed_lab_unit_ids = get_user_lab_unit_ids_no_admin_override(current_user.id)
        if encounter.lab_unit_id not in allowed_lab_unit_ids:
            return jsonify({"success": False, "message": "Permission denied"}), 403

        # Check if grading tasks are in progress
        task_states = db.execute(
            select(GradingTask.state).where(GradingTask.patient_encounter_id == encounter.id)
        ).scalars().all()
        if any(s and s.lower() != 'pending' for s in task_states):
            return jsonify({
                "success": False,
                "message": "Cannot modify image while associated grading tasks are in progress."
            }), 409

        if not img.edited_filename:
            return jsonify({"success": True, "message": "No edited version to restore."}), 200

        # Delete the edited file
        edited_path = abs_from_parts(img.folder_rel, img.edited_filename, kind="edited")
        try:
            from pathlib import Path
            Path(edited_path).unlink(missing_ok=True)
        except Exception as e:
            current_app.logger.warning("Failed to delete edited file %s: %s", edited_path, e)

        img.edited_filename = None
        bump_media_cache_version(str(img.uuid))

        return jsonify({"success": True, "message": "Original image restored."})


@bp.route("/mark_not_gradable/<uuid>", methods=["POST"])
@login_required
@roles_required("admin", "optometrist", "data_manager")
def mark_not_gradable(uuid):
    """Mark an image as not gradable with a reason."""
    from utils.upload_eligibility import get_user_lab_unit_ids_no_admin_override

    data = request.json
    reason = data.get("reason", "").strip() if data else None

    if not reason:
        return jsonify({"success": False, "message": "Reason is required"}), 400

    with transaction_scope() as db:
        img = db.query(EncounterSetImage).filter_by(uuid=uuid).first()
        if not img:
            return jsonify({"success": False, "message": "Image not found"}), 404

        encounter = db.query(PatientEncounters).filter_by(id=img.patient_encounter_id).first()
        if not encounter:
            return jsonify({"success": False, "message": "Encounter not found"}), 404

        # Check access
        allowed_lab_unit_ids = get_user_lab_unit_ids_no_admin_override(current_user.id)
        if encounter.lab_unit_id not in allowed_lab_unit_ids:
            return jsonify({"success": False, "message": "Permission denied"}), 403

        img.is_not_gradable = True
        img.not_gradable_reason = reason
        img.is_reviewed = True  # Mark as reviewed even if not gradable

        return jsonify({"success": True})


@bp.route("/undo_not_gradable/<uuid>", methods=["POST"])
@login_required
@roles_required("admin", "optometrist", "data_manager")
def undo_not_gradable(uuid):
    """Undo the not gradable status for an image."""
    from utils.upload_eligibility import get_user_lab_unit_ids_no_admin_override

    with transaction_scope() as db:
        img = db.query(EncounterSetImage).filter_by(uuid=uuid).first()
        if not img:
            return jsonify({"success": False, "message": "Image not found"}), 404

        encounter = db.query(PatientEncounters).filter_by(id=img.patient_encounter_id).first()
        if not encounter:
            return jsonify({"success": False, "message": "Encounter not found"}), 404

        # Check access
        allowed_lab_unit_ids = get_user_lab_unit_ids_no_admin_override(current_user.id)
        if encounter.lab_unit_id not in allowed_lab_unit_ids:
            return jsonify({"success": False, "message": "Permission denied"}), 403

        img.is_not_gradable = False
        img.not_gradable_reason = None
        # Keep is_reviewed = True since it was reviewed

        return jsonify({"success": True})
