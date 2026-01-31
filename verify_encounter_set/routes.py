from flask import render_template, abort, current_app, flash, redirect, url_for, request, jsonify
from flask_login import login_required, current_user
from auth.roles import roles_required
from models import PatientEncounters, EncounterSetImage, Disease
from db_transaction_manager import transaction_scope
from utils.utils import with_session
from . import bp

@bp.route("/")
@login_required
@roles_required("admin", "optometrist", "data_manager")
def index():
    """List encounter sets pending verification."""
    with transaction_scope() as db:
        # Get encounters that are set-based and NOT yet verified
        # For now, let's assume encounter_verified_status = 'pending' or NULL for new sets
        encounters = db.query(PatientEncounters).filter(
            PatientEncounters.is_set_based == True,
            PatientEncounters.encounter_verified_status.in_(['pending', None])
        ).order_by(PatientEncounters.id.desc()).all()
        
        return render_template("verify_encounter_set/index.html", encounters=encounters)

@bp.route("/verify/<uuid>")
@login_required
@roles_required("admin", "optometrist", "data_manager")
def verify_encounter(uuid):
    """View and manage a specific encounter set for verification."""
    with transaction_scope() as db:
        encounter = db.query(PatientEncounters).filter_by(uuid=uuid).first()
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
    # Potential task creation import
    # from tasks.taskCreationServices import create_grading_task_for_encounter_set
    
    with transaction_scope() as db:
        encounter = db.query(PatientEncounters).filter_by(uuid=uuid).first()
        if not encounter:
            abort(404)
            
        encounter.encounter_verified_status = 'verified'
        encounter.encounter_verified_by = current_user.username
        encounter.encounter_verified_at = utcnow()
        
        # TODO: Trigger GradingTask creation
        # This will depend on the disease and lab unit
        
        flash(f"Encounter set {encounter.name} verified successfully.", "success")
        return redirect(url_for("verify_encounter_set.index"))
