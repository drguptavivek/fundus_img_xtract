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


# -------------------
# Lab Units API
# -------------------

@api_bp.route('/hospitals/<int:hospital_id>/labunits', methods=['GET'])
@login_required
@roles_required("admin", "local_admin", "data_manager", "ophthalmologist", "resident", "optometrist")
def get_lab_units_by_hospital(hospital_id):
    """Get all lab units for a specific hospital."""
    with get_db_session() as db:
        # Check if hospital exists
        hospital = db.get(Hospital, hospital_id)
        if not hospital:
            return jsonify({"error": "Hospital not found"}), 404
        
        # Get lab units for the hospital
        lab_units = db.execute(
            select(LabUnit)
            .where(LabUnit.hospital_id == hospital_id)
            .order_by(LabUnit.name.asc())
        ).scalars().all()
        
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
@roles_required("admin", "local_admin", "data_manager", "ophthalmologist", "resident", "optometrist")
def get_all_lab_units_list():
    """Get all lab units."""
    with get_db_session() as db:
        lab_units = db.execute(
            select(LabUnit)
            .options(selectinload(LabUnit.hospital))
            .order_by(LabUnit.name.asc())
        ).scalars().all()
        
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
@roles_required("admin", "local_admin", "data_manager", "ophthalmologist", "resident", "optometrist")
def get_lab_unit_by_id(lab_unit_id):
    """Get a specific lab unit by ID."""
    with get_db_session() as db:
        lab_unit = db.get(LabUnit, lab_unit_id)
        if not lab_unit:
            return jsonify({"error": "Lab unit not found"}), 404
        
        lab_unit_data = {
            "id": lab_unit.id,
            "name": lab_unit.name,
            "hospital_id": lab_unit.hospital_id,
            "hospital_name": lab_unit.hospital.name if lab_unit.hospital else None
        }
        
        return jsonify(lab_unit_data)
