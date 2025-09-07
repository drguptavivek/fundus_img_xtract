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

@api_bp.route('/users/<int:user_id>/lab-units', methods=['GET'])
@login_required
def get_user_lab_units(user_id):
    """Get all lab units for a specific user."""
    with Session() as db:
        user = db.get(User, user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        # Check if current user can access this user's data
        from flask_login import current_user
        if not (current_user.has_role('admin', 'data_manager') or current_user.id == user_id):
            return jsonify({"error": "Forbidden"}), 403
        
        lab_units = user.lab_units
        
        return jsonify([{
            "id": lu.id,
            "name": lu.name,
            "hospital_id": lu.hospital_id,
            "hospital_name": lu.hospital.name if lu.hospital else None,
            "created_at": lu.created_at.isoformat() if lu.created_at else None
        } for lu in lab_units])


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
            "created_at": h.created_at.isoformat() if h.created_at else None
        } for h in hospitals])