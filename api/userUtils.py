from flask import jsonify
from flask_login import current_user, login_required
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from authz.behaviors import clinical_hospitals, clinical_lab_units
from models import Hospital, LabUnit
from auth.roles import roles_required
from utils.utils import get_db_session
from . import api_bp

@api_bp.route("/eligibleLabUnit", methods=["GET"])
@login_required
@roles_required(
    "admin",
    "local_admin",
    "data_manager",
    "ophthalmologist",
    "optometrist",
    "fileUploader",
)
def get_eligible_lab_units():
    """Return Lab Units visible through the route's clinical scope behaviour."""
    with get_db_session() as db:
        query = clinical_lab_units(
            db,
            select(LabUnit).options(selectinload(LabUnit.hospital)),
            current_user,
        )
        lab_units = db.execute(query.order_by(LabUnit.name)).scalars().all()
        eligible_lab_units = [
            {
                'id': lab_unit.id,
                'name': lab_unit.name,
                'hospital_id': lab_unit.hospital_id,
                'hospital_name': lab_unit.hospital.name if lab_unit.hospital else None
            }
            for lab_unit in lab_units
        ]
        
        return jsonify({
            'user_id': current_user.id,
            'hospital_id': None if current_user.has_role('admin') else current_user.hospital_id,
            'is_master_admin': current_user.has_role('admin'),
            'eligible_lab_units': eligible_lab_units
        })
    

@api_bp.route("/eligibleLabUnitCurrentUser", methods=["GET"])
@login_required
@roles_required(
    "admin",
    "local_admin",
    "data_manager",
    "ophthalmologist",
    "optometrist",
    "fileUploader",
)
def get_eligible_lab_units_currentUser():
    """Return the current actor's authorized Lab Unit and Hospital choices."""
    with get_db_session() as db:
        lab_query = clinical_lab_units(
            db,
            select(LabUnit).options(selectinload(LabUnit.hospital)),
            current_user,
        )
        hospital_query = clinical_hospitals(db, select(Hospital), current_user)
        lab_units = db.execute(lab_query.order_by(LabUnit.name)).scalars().all()
        hospitals = db.execute(hospital_query.order_by(Hospital.name)).scalars().all()

        eligible_lab_units = [
            {
                'id': lab_unit.id,
                'name': lab_unit.name,
                'hospital_id': lab_unit.hospital_id,
                'hospital_name': lab_unit.hospital.name if lab_unit.hospital else None
            }
            for lab_unit in lab_units
        ]
        
        # Format the hospitals
        eligible_hospitals = [
            {
                'id': hospital.id,
                'name': hospital.name
            }
            for hospital in hospitals
        ]
        
        return jsonify({
            'user_id': current_user.id,
            'hospital_id': None if current_user.has_role('admin') else current_user.hospital_id,
            'is_master_admin': current_user.has_role('admin'),
            'eligible_lab_units': eligible_lab_units,
            'eligible_hospitals': eligible_hospitals
        })
