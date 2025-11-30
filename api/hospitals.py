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


# -------------------
# Hospital API
# -------------------

@api_bp.route('/hospitals', methods=['GET'])
@login_required
@roles_required("admin", "local_admin", "data_manager", "ophthalmologist", "resident", "optometrist", "fileUploader")
def get_hospitals_list():
    """Get all hospitals."""
    with get_db_session() as db:
        allowed_lab_unit_ids = get_user_lab_unit_ids_no_admin_override(current_user.id)
        if not allowed_lab_unit_ids:
            return jsonify([])

        allowed_hospital_ids = set(
            db.execute(
                select(LabUnit.hospital_id).where(LabUnit.id.in_(allowed_lab_unit_ids))
            ).scalars()
        )

        hospitals = db.execute(
            select(Hospital)
            .where(Hospital.id.in_(allowed_hospital_ids))
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
@roles_required("admin", "local_admin", "data_manager", "ophthalmologist", "resident", "optometrist", "fileUploader")
def get_hospital_by_id(hospital_id):
    """Get a specific hospital by ID."""
    with get_db_session() as db:
        hospital = db.get(Hospital, hospital_id)
        if not hospital:
            return jsonify({"error": "Hospital not found"}), 404

        allowed_lab_unit_ids = get_user_lab_unit_ids_no_admin_override(current_user.id)
        if not allowed_lab_unit_ids:
            return jsonify({"error": "Forbidden"}), 403

        allowed_hospital_ids = set(
            db.execute(
                select(LabUnit.hospital_id).where(LabUnit.id.in_(allowed_lab_unit_ids))
            ).scalars()
        )
        if hospital_id not in allowed_hospital_ids:
            return jsonify({"error": "Forbidden"}), 403

        hospital_data = {
            "id": hospital.id,
            "name": hospital.name
        }
        
        return jsonify(hospital_data)
