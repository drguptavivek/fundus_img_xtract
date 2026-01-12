# api/hospitals.py
from flask import jsonify, request
from flask_login import login_required, current_user
from sqlalchemy import select
from sqlalchemy.orm import selectinload

# Import the blueprint
from . import api_bp

# Import utility functions and models
from auth.roles import roles_required
from db_transaction_manager import get_db_session
from models import Hospital, LabUnit
from utils.upload_eligibility import get_user_lab_unit_ids_no_admin_override
from utils.hospital_scoping import apply_scoping


# -------------------
# Hospital API
# -------------------

@api_bp.route('/hospitals', methods=['GET'])
@login_required
@roles_required("admin", "local_admin", "data_manager", "ophthalmologist", "resident", "optometrist", "fileUploader")
def get_hospitals_list():
    """Get accessible hospitals for current user (hospital-aware)."""
    with get_db_session() as db:
        query = select(Hospital).order_by(Hospital.name.asc())
        query = apply_scoping(query, Hospital, current_user, "view")
        hospitals = db.execute(query).scalars().all()

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
@roles_required("admin", "local_admin", "data_manager", "ophthalmologist", "resident", "optometrist", "fileUploader")
def get_hospital_by_id(hospital_id):
    """Get a specific hospital by ID (hospital-aware)."""
    with get_db_session() as db:
        query = select(Hospital).where(Hospital.id == hospital_id)
        query = apply_scoping(query, Hospital, current_user, "view")
        hospital = db.execute(query).scalar_one_or_none()
        
        if not hospital:
            return jsonify({"error": "Hospital not found or access denied"}), 404

        hospital_data = {
            "id": hospital.id,
            "name": hospital.name
        }
        
        return jsonify(hospital_data)
