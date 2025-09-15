# api/comprehensive.py
from flask import jsonify
from sqlalchemy import select

# Import the blueprint
from . import api_bp

# Import utility functions and models
from auth.roles import roles_required, login_required
from models import Session, User, Hospital, LabUnit, Disease


# -------------------
# Comprehensive User Data API
# -------------------

@api_bp.route('/users/<int:user_id>/comprehensive', methods=['GET'])
@login_required
def get_user_comprehensive(user_id):
    """Get comprehensive information for a specific user including hospitals, lab units, and specializations."""
    with Session() as db:
        user = db.get(User, user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        # Check if current user can access this user's data
        from flask_login import current_user
        if not (current_user.has_role('admin', 'data_manager') or current_user.id == user_id):
            return jsonify({"error": "Forbidden"}), 403
        
        # Get user's lab units
        lab_units = user.lab_units
        
        # Get user's hospitals through lab units
        hospital_ids = list(set(lu.hospital_id for lu in lab_units))
        hospitals = db.execute(
            select(Hospital)
            .where(Hospital.id.in_(hospital_ids))
            .order_by(Hospital.name)
        ).scalars().all()
        
        # Get user's disease specializations
        # Disease specializations (removed as part of cleanup)
        
        return jsonify({
            "user": {
                "id": user.id,
                "username": user.username,
                "full_name": user.full_name,
                "email": user.email,
                "is_active": user.is_active,
                "roles": [r.name for r in user.roles]
            },
            "hospitals": [{
                "id": h.id,
                "name": h.name
            } for h in hospitals],
            "lab_units": [{
                "id": lu.id,
                "name": lu.name,
                "hospital_id": lu.hospital_id,
                "hospital_name": lu.hospital.name if lu.hospital else None
            } for lu in lab_units],
            "specializations": [{
                "id": d.id,
                "name": d.name
            } for d in specializations],
            "hospital_ids": hospital_ids,
            "lab_unit_ids": [lu.id for lu in lab_units],
            "lab_unit_names": [lu.name for lu in lab_units],
            "specialization_ids": [d.id for d in specializations],
            "specialization_names": [d.name for d in specializations]
        })