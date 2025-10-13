# api/hospitals.py
from flask import jsonify, request
from flask_login import login_required, current_user
from sqlalchemy import select
from sqlalchemy.orm import selectinload

# Import the blueprint
from . import api_bp

# Import utility functions and models
from auth.roles import roles_required
from models import Session, Hospital, LabUnit


# -------------------
# Hospital API
# -------------------

@api_bp.route('/hospitals', methods=['GET'])
@login_required
@roles_required("admin", "data_manager", "ophthalmologist", "resident", "optometrist")
def get_hospitals_list():
    """Get all hospitals."""
    with Session() as db:
        hospitals = db.execute(
            select(Hospital)
            .order_by(Hospital.name.asc())
        ).scalars().all()
        
        hospitals_data = [
            {
                "id": hospital.id,
                "name": hospital.name
            }
            for hospital in hospitals
        ]
        
        return jsonify(hospitals_data)


@api_bp.route('/hospitals/<int:hospital_id>', methods=['GET'])
@login_required
@roles_required("admin", "data_manager", "ophthalmologist", "resident", "optometrist")
def get_hospital_by_id(hospital_id):
    """Get a specific hospital by ID."""
    with Session() as db:
        hospital = db.get(Hospital, hospital_id)
        if not hospital:
            return jsonify({"error": "Hospital not found"}), 404
        
        hospital_data = {
            "id": hospital.id,
            "name": hospital.name
        }
        
        return jsonify(hospital_data)