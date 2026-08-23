# api/labUnits.py
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
# Lab Units API
# -------------------

@api_bp.route('/hospitals/<int:hospital_id>/labunits', methods=['GET'])
@login_required
@roles_required(
    "admin",
    "local_admin",
    "data_manager",
    "ophthalmologist",
    "optometrist",
    "fileUploader",
)
def get_lab_units_by_hospital(hospital_id):
    """Get all lab units for a specific hospital."""
    with get_db_session() as db:
        # Get lab units for the hospital
        query = (
            select(LabUnit)
            .where(LabUnit.hospital_id == hospital_id)
            .order_by(LabUnit.name.asc())
        )
        query = apply_scoping(query, LabUnit, current_user, "view")
        lab_units = db.execute(query).scalars().all()
        
        lab_units_data = [
            {
                "id": lab_unit.id,
                "name": lab_unit.name,
                "hospital_id": lab_unit.hospital_id
            }
            for lab_unit in lab_units
        ]
        
        return jsonify(lab_units_data)


@api_bp.route('/labunits', methods=['GET'])
@login_required
@roles_required(
    "admin",
    "local_admin",
    "data_manager",
    "ophthalmologist",
    "optometrist",
    "fileUploader",
)
def get_all_lab_units_list():
    """Get all lab units."""
    with get_db_session() as db:
        query = (
            select(LabUnit)
            .options(selectinload(LabUnit.hospital))
            .order_by(LabUnit.name.asc())
        )
        query = apply_scoping(query, LabUnit, current_user, "view")
        lab_units = db.execute(query).scalars().all()
        
        lab_units_data = [
            {
                "id": lab_unit.id,
                "name": lab_unit.name,
                "hospital_id": lab_unit.hospital_id,
                "hospital_name": lab_unit.hospital.name if lab_unit.hospital else None
            }
            for lab_unit in lab_units
        ]
        
        return jsonify(lab_units_data)


@api_bp.route('/labunits/<int:lab_unit_id>', methods=['GET'])
@login_required
@roles_required(
    "admin",
    "local_admin",
    "data_manager",
    "ophthalmologist",
    "optometrist",
    "fileUploader",
)
def get_lab_unit_by_id(lab_unit_id):
    """Get a specific lab unit by ID."""
    with get_db_session() as db:
        query = select(LabUnit).where(LabUnit.id == lab_unit_id).options(selectinload(LabUnit.hospital))
        query = apply_scoping(query, LabUnit, current_user, "view")
        lab_unit = db.execute(query).scalar_one_or_none()
        
        if not lab_unit:
            return jsonify({"error": "Lab unit not found or access denied"}), 404
        
        lab_unit_data = {
            "id": lab_unit.id,
            "name": lab_unit.name,
            "hospital_id": lab_unit.hospital_id,
            "hospital_name": lab_unit.hospital.name if lab_unit.hospital else None
        }
        
        return jsonify(lab_unit_data)
