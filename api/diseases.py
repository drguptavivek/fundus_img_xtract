# api/diseases.py
from flask import jsonify
from sqlalchemy import select
from sqlalchemy.orm import selectinload

# Import the blueprint
from . import api_bp

# Import utility functions and models
from auth.roles import roles_required
from models import Session, Disease, DiseaseGrading, User


# -------------------
# Diseases API
# -------------------

@api_bp.route('/diseases', methods=['GET'])
@roles_required("admin", "data_manager", "ophthalmologist")
def get_diseases():
    """Get all diseases."""
    with Session() as db:
        diseases = db.execute(select(Disease).order_by(Disease.name)).scalars().all()
        return jsonify([{
            "id": d.id,
            "name": d.name,
        } for d in diseases])


@api_bp.route('/diseases/<int:disease_id>', methods=['GET'])
@roles_required("admin", "data_manager", "ophthalmologist")
def get_disease(disease_id):
    """Get a specific disease by ID."""
    with Session() as db:
        disease = db.get(Disease, disease_id)
        if not disease:
            return jsonify({"error": "Disease not found"}), 404
        return jsonify({
            "id": disease.id,
            "name": disease.name,
        })


@api_bp.route('/diseases/<int:disease_id>/gradings', methods=['GET'])
@roles_required("admin", "data_manager", "ophthalmologist")
def get_disease_gradings(disease_id):
    """Get all gradings for a specific disease."""
    with Session() as db:
        disease = db.get(Disease, disease_id)
        if not disease:
            return jsonify({"error": "Disease not found"}), 404
        
        gradings = db.execute(
            select(DiseaseGrading)
            .where(DiseaseGrading.disease_id == disease_id)
            .where(DiseaseGrading.is_active == True)
            .order_by(DiseaseGrading.display_order)
        ).scalars().all()
        
        return jsonify([{
            "id": g.id,
            "disease_id": g.disease_id,
            "impression": g.impression,
            "display_order": g.display_order,
            "is_active": g.is_active
        } for g in gradings])


@api_bp.route('/diseases/<int:disease_id>/specialists', methods=['GET'])
@roles_required("admin", "data_manager")
def get_disease_specialists(disease_id):
    """Get all users specialized in a specific disease."""
    with Session() as db:
        disease = db.get(Disease, disease_id)
        if not disease:
            return jsonify({"error": "Disease not found"}), 404
        
        specialists = db.execute(
            select(User)
            # Removed join with User.disease_specializations as part of cleanup
            .where(Disease.id == disease_id)
            .order_by(User.username)
        ).scalars().all()
        
        return jsonify([{
            "id": s.id,
            "username": s.username,
            "full_name": s.full_name,
            "email": s.email,
            "hospital_ids": [lu.hospital_id for lu in s.lab_units],
            "lab_unit_ids": [lu.id for lu in s.lab_units],
            "lab_unit_names": [lu.name for lu in s.lab_units]
        } for s in specialists])