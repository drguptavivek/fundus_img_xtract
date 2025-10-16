from flask import jsonify, request
from flask_login import current_user, login_required
from models import LabUnit, Session, User
from auth.roles import roles_required, login_required
from utils.upload_eligibility import get_user_lab_unit_ids
from . import api_bp

@api_bp.route("/eligibleLabUnit", methods=["GET"])
@login_required
def get_eligible_lab_units():
    """API endpoint to get eligible lab units for the current user or a specified user ID."""
    db = Session()
    try:
        # Check if a specific user ID is provided in the query parameters
        user_id_param = request.args.get("user_id", type=int)
        
        # If user_id is provided and the current user is admin, use that user_id
        # Otherwise, use the current user's ID
        if user_id_param and current_user.has_role("admin"):
            user_id = user_id_param
        else:
            user_id = current_user.id
        
        # Get the user's eligible lab unit IDs
        lab_unit_ids = get_user_lab_unit_ids(user_id)
        
        # Get the lab unit details from the database
        lab_units = db.query(LabUnit).filter(LabUnit.id.in_(list(lab_unit_ids))).all()
        
        # Format the results
        eligible_lab_units = [
            {
                'id': lab_unit.id,
                'name': lab_unit.name,
                'hospital_id': lab_unit.hospital_id,
                'hospital_name': lab_unit.hospital.name if lab_unit.hospital else None
            }
            for lab_unit in lab_units
        ]
        
        return jsonify({
            'user_id': user_id,
            'eligible_lab_units': eligible_lab_units
        })
    finally:
        db.close()