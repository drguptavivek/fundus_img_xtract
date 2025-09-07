# api/hospitals.py
from flask import jsonify
from sqlalchemy import select
from sqlalchemy.orm import selectinload

# Import the blueprint
from . import api_bp

# Import utility functions and models
from auth.roles import roles_required
from models import Session, Hospital, LabUnit, User, Disease


# -------------------
# Hospitals API
# -------------------

@api_bp.route('/hospitals', methods=['GET'])
@roles_required("admin", "data_manager")
def get_hospitals():
    """Get all hospitals."""
    with Session() as db:
        hospitals = db.execute(select(Hospital).order_by(Hospital.name)).scalars().all()
        return jsonify([{
            "id": h.id,
            "name": h.name,
        } for h in hospitals])


@api_bp.route('/hospitals/<int:hospital_id>', methods=['GET'])
@roles_required("admin", "data_manager")
def get_hospital_by_id(hospital_id):
    """Get a specific hospital by ID."""
    with Session() as db:
        hospital = db.get(Hospital, hospital_id)
        if not hospital:
            return jsonify({"error": "Hospital not found"}), 404
        return jsonify({
            "id": hospital.id,
            "name": hospital.name,
        })


@api_bp.route('/hospitals/<int:hospital_id>/lab-units', methods=['GET'])
@roles_required("admin", "data_manager")
def get_hospital_lab_units(hospital_id):
    """Get all lab units for a specific hospital."""
    with Session() as db:
        hospital = db.get(Hospital, hospital_id)
        if not hospital:
            return jsonify({"error": "Hospital not found"}), 404
        
        lab_units = db.execute(
            select(LabUnit)
            .where(LabUnit.hospital_id == hospital_id)
            .order_by(LabUnit.name)
        ).scalars().all()
        
        return jsonify([{
            "id": lu.id,
            "name": lu.name,
            "hospital_id": lu.hospital_id,
        } for lu in lab_units])


@api_bp.route('/hospitals/<int:hospital_id>/specializations/<int:disease_id>/users', methods=['GET'])
@roles_required("admin", "data_manager")
def get_hospital_disease_specialists(hospital_id, disease_id):
    """Get all users specialized in a specific disease at a hospital."""
    with Session() as db:
        # Check if hospital exists
        hospital = db.get(Hospital, hospital_id)
        if not hospital:
            return jsonify({"error": "Hospital not found"}), 404
        
        # Check if disease exists
        disease = db.get(Disease, disease_id)
        if not disease:
            return jsonify({"error": "Disease not found"}), 404
        
        # Get users with the specified specialization who are associated with this hospital
        # Users are associated with a hospital through their lab units
        users = db.execute(
            select(User)
            .join(User.lab_units)
            .join(LabUnit.hospital)
            .join(User.disease_specializations)
            .where(Hospital.id == hospital_id)
            .where(Disease.id == disease_id)
            .order_by(User.username)
        ).scalars().all()
        
        return jsonify([{
            "id": u.id,
            "username": u.username,
            "full_name": u.full_name,
            "email": u.email
        } for u in users])