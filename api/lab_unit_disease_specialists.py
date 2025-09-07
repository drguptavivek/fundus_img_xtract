# api/lab_unit_disease_specialists.py
from flask import jsonify
from sqlalchemy import select

# Import the blueprint
from . import api_bp

# Import utility functions and models
from auth.roles import roles_required, login_required
from models import Session, LabUnit, Disease, User


# -------------------
# Lab Unit Disease Specialists API
# -------------------

@api_bp.route('/lab-units/<int:lab_unit_id>/diseases/<int:disease_id>/ophthalmologists', methods=['GET'])
@login_required
def get_lab_unit_disease_ophthalmologists(lab_unit_id, disease_id):
    """Get a simple array of ophthalmologist user IDs for a specific disease at a lab unit."""
    with Session() as db:
        # Check if lab unit exists
        lab_unit = db.get(LabUnit, lab_unit_id)
        if not lab_unit:
            return jsonify({"error": "Lab unit not found"}), 404
        
        # Check if disease exists
        disease = db.get(Disease, disease_id)
        if not disease:
            return jsonify({"error": "Disease not found"}), 404
        
        # Check if current user can access this lab unit's data
        from flask_login import current_user
        if not (current_user.has_role('admin') or 
                any(lu.id == lab_unit_id for lu in current_user.lab_units)):
            return jsonify({"error": "Forbidden"}), 403
        
        # Get all users associated with this lab unit
        lab_unit_users = db.execute(
            select(User)
            .join(User.lab_units)
            .where(LabUnit.id == lab_unit_id)
        ).scalars().all()
        
        # Filter users who are specialized in this disease and are ophthalmologists
        ophthalmologist_ids = []
        for user in lab_unit_users:
            if disease in user.disease_specializations:
                role_names = [role.name for role in user.roles]
                if "ophthalmologist" in role_names:
                    ophthalmologist_ids.append(user.id)
        
        return jsonify(ophthalmologist_ids)


@api_bp.route('/lab-units/<int:lab_unit_id>/diseases/<int:disease_id>/residents', methods=['GET'])
@login_required
def get_lab_unit_disease_residents(lab_unit_id, disease_id):
    """Get a simple array of resident user IDs for a specific disease at a lab unit."""
    with Session() as db:
        # Check if lab unit exists
        lab_unit = db.get(LabUnit, lab_unit_id)
        if not lab_unit:
            return jsonify({"error": "Lab unit not found"}), 404
        
        # Check if disease exists
        disease = db.get(Disease, disease_id)
        if not disease:
            return jsonify({"error": "Disease not found"}), 404
        
        # Check if current user can access this lab unit's data
        from flask_login import current_user
        if not (current_user.has_role('admin') or 
                any(lu.id == lab_unit_id for lu in current_user.lab_units)):
            return jsonify({"error": "Forbidden"}), 403
        
        # Get all users associated with this lab unit
        lab_unit_users = db.execute(
            select(User)
            .join(User.lab_units)
            .where(LabUnit.id == lab_unit_id)
        ).scalars().all()
        
        # Filter users who are specialized in this disease and are residents
        resident_ids = []
        for user in lab_unit_users:
            if disease in user.disease_specializations:
                role_names = [role.name for role in user.roles]
                if "resident" in role_names:
                    resident_ids.append(user.id)
        
        return jsonify(resident_ids)


@api_bp.route('/lab-units/<int:lab_unit_id>/diseases/<int:disease_id>/specialists', methods=['GET'])
@login_required
def get_lab_unit_disease_specialists(lab_unit_id, disease_id):
    """Get all specialists (ophthalmologists and residents) for a specific disease at a lab unit."""
    with Session() as db:
        # Check if lab unit exists
        lab_unit = db.get(LabUnit, lab_unit_id)
        if not lab_unit:
            return jsonify({"error": "Lab unit not found"}), 404
        
        # Check if disease exists
        disease = db.get(Disease, disease_id)
        if not disease:
            return jsonify({"error": "Disease not found"}), 404
        
        # Check if current user can access this lab unit's data
        from flask_login import current_user
        if not (current_user.has_role('admin') or 
                any(lu.id == lab_unit_id for lu in current_user.lab_units)):
            return jsonify({"error": "Forbidden"}), 403
        
        # Get all users associated with this lab unit
        lab_unit_users = db.execute(
            select(User)
            .join(User.lab_units)
            .where(LabUnit.id == lab_unit_id)
        ).scalars().all()
        
        # Filter users who are specialized in this disease
        specialists = [user for user in lab_unit_users if disease in user.disease_specializations]
        
        # Separate ophthalmologists and residents
        ophthalmologists = []
        residents = []
        
        for specialist in specialists:
            role_names = [role.name for role in specialist.roles]
            
            specialist_data = {
                "id": specialist.id,
                "username": specialist.username,
                "full_name": specialist.full_name,
                "email": specialist.email
            }
            
            if "ophthalmologist" in role_names:
                ophthalmologists.append(specialist_data)
            elif "resident" in role_names:
                residents.append(specialist_data)
        
        return jsonify({
            "lab_unit": {
                "id": lab_unit.id,
                "name": lab_unit.name,
                "hospital_id": lab_unit.hospital_id
            },
            "disease": {
                "id": disease.id,
                "name": disease.name
            },
            "ophthalmologists": ophthalmologists,
            "residents": residents,
            "total_specialists": len(specialists)
        })


@api_bp.route('/lab-units/<int:lab_unit_id>/specialists-summary', methods=['GET'])
@login_required
def get_lab_unit_specialists_summary(lab_unit_id):
    """Get a summary of all specialists (ophthalmologists and residents) for each disease at a lab unit."""
    with Session() as db:
        # Check if lab unit exists
        lab_unit = db.get(LabUnit, lab_unit_id)
        if not lab_unit:
            return jsonify({"error": "Lab unit not found"}), 404
        
        # Check if current user can access this lab unit's data
        from flask_login import current_user
        if not (current_user.has_role('admin') or 
                any(lu.id == lab_unit_id for lu in current_user.lab_units)):
            return jsonify({"error": "Forbidden"}), 403
        
        # Get all users associated with this lab unit
        lab_unit_users = db.execute(
            select(User)
            .join(User.lab_units)
            .where(LabUnit.id == lab_unit_id)
        ).scalars().all()
        
        # Get all diseases
        diseases = db.execute(select(Disease)).scalars().all()
        
        # Build summary for each disease
        disease_summary = []
        
        for disease in diseases:
            # Filter users who are specialized in this disease
            specialists = [user for user in lab_unit_users if disease in user.disease_specializations]
            
            # Separate ophthalmologists and residents
            ophthalmologists = []
            residents = []
            
            for specialist in specialists:
                role_names = [role.name for role in specialist.roles]
                
                specialist_data = {
                    "id": specialist.id,
                    "username": specialist.username,
                    "full_name": specialist.full_name,
                    "email": specialist.email
                }
                
                if "ophthalmologist" in role_names:
                    ophthalmologists.append(specialist_data)
                elif "resident" in role_names:
                    residents.append(specialist_data)
            
            if specialists:  # Only include diseases that have specialists
                disease_summary.append({
                    "disease": {
                        "id": disease.id,
                        "name": disease.name
                    },
                    "ophthalmologists": ophthalmologists,
                    "ophthalmologist_count": len(ophthalmologists),
                    "residents": residents,
                    "resident_count": len(residents),
                    "total_specialists": len(specialists)
                })
        
        return jsonify({
            "lab_unit": {
                "id": lab_unit.id,
                "name": lab_unit.name,
                "hospital_id": lab_unit.hospital_id
            },
            "diseases": disease_summary
        })