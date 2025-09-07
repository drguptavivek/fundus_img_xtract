# api/lab_units.py
from flask import jsonify
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

# Import the blueprint
from . import api_bp

# Import utility functions and models
from auth.roles import roles_required, login_required
from models import Session, LabUnit, Hospital, User, DirectImageUpload


# -------------------
# Lab Units API
# -------------------

@api_bp.route('/lab-units/<int:lab_unit_id>', methods=['GET'])
@roles_required("admin", "data_manager")
def get_lab_unit(lab_unit_id):
    """Get a specific lab unit by ID."""
    with Session() as db:
        lab_unit = db.get(LabUnit, lab_unit_id)
        if not lab_unit:
            return jsonify({"error": "Lab unit not found"}), 404
        return jsonify({
            "id": lab_unit.id,
            "name": lab_unit.name,
            "hospital_id": lab_unit.hospital_id,
            "hospital_name": lab_unit.hospital.name if lab_unit.hospital else None,
            "created_at": lab_unit.created_at.isoformat() if lab_unit.created_at else None
        })


@api_bp.route('/lab-units/<int:lab_unit_id>/users', methods=['GET'])
@login_required
def get_lab_unit_users(lab_unit_id):
    """Get all users assigned to a specific lab unit."""
    with Session() as db:
        lab_unit = db.get(LabUnit, lab_unit_id)
        if not lab_unit:
            return jsonify({"error": "Lab unit not found"}), 404
        
        # Check if current user can access this lab unit's data
        from flask_login import current_user
        if not (current_user.has_role('admin', 'data_manager') or 
                any(lu.id == lab_unit_id for lu in current_user.lab_units)):
            return jsonify({"error": "Forbidden"}), 403
        
        users = db.execute(
            select(User)
            .join(User.lab_units)
            .where(LabUnit.id == lab_unit_id)
            .order_by(User.username)
        ).scalars().all()
        
        return jsonify([{
            "id": u.id,
            "username": u.username,
            "full_name": u.full_name,
            "email": u.email,
            "is_active": u.is_active,
            "hospital_ids": [lu.hospital_id for lu in u.lab_units],
            "lab_unit_ids": [lu.id for lu in u.lab_units],
            "lab_unit_names": [lu.name for lu in u.lab_units]
        } for u in users])


@api_bp.route('/lab-units/<int:lab_unit_id>/upload-count', methods=['GET'])
@roles_required("admin", "data_manager")
def get_lab_unit_upload_count(lab_unit_id):
    """Get the count of uploads for a specific lab unit."""
    with Session() as db:
        lab_unit = db.get(LabUnit, lab_unit_id)
        if not lab_unit:
            return jsonify({"error": "Lab unit not found"}), 404
        
        upload_count = db.execute(
            select(func.count())
            .select_from(DirectImageUpload)
            .where(DirectImageUpload.lab_unit_id == lab_unit_id)
        ).scalar_one()
        
        return jsonify({
            "lab_unit_id": lab_unit_id,
            "upload_count": upload_count
        })