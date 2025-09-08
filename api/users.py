# api/users.py
from flask import jsonify
from sqlalchemy import select
from sqlalchemy.orm import selectinload

# Import the blueprint
from . import api_bp

# Import utility functions and models
from auth.roles import roles_required, login_required
from models import Session, User, Hospital, LabUnit


# -------------------
# Users API
# -------------------




@api_bp.route('/users/<int:user_id>/hospitals', methods=['GET'])
@login_required
def get_user_hospitals(user_id):
    """Get all hospitals for a specific user (through their lab units)."""
    with Session() as db:
        user = db.get(User, user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        # Check if current user can access this user's data
        from flask_login import current_user
        if not (current_user.has_role('admin', 'data_manager') or current_user.id == user_id):
            return jsonify({"error": "Forbidden"}), 403
        
        # Get distinct hospitals through user's lab units
        hospitals = db.execute(
            select(Hospital)
            .join(LabUnit)
            .where(LabUnit.id.in_([lu.id for lu in user.lab_units]))
            .order_by(Hospital.name)
        ).scalars().all()
        
        return jsonify([{
            "id": h.id,
            "name": h.name,
            "lab_unit_ids": [lu.id for lu in user.lab_units if lu.hospital_id == h.id],
            "lab_unit_names": [lu.name for lu in user.lab_units if lu.hospital_id == h.id]
        } for h in hospitals])
