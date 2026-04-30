from flask import jsonify, request
from flask_login import current_user, login_required
from models import LabUnit, User, Hospital
from auth.roles import roles_required
from utils.upload_eligibility import get_user_lab_unit_ids_no_admin_override
from utils.utils import get_db_session
from . import api_bp

@api_bp.route("/eligibleLabUnit", methods=["GET"])
@login_required
@roles_required("admin", "local_admin", "data_manager", "ophthalmologist", "resident", "optometrist", "fileUploader")
def get_eligible_lab_units():
    """API endpoint to get eligible lab units for the current user (hospital-aware)."""
    from utils.hospital_scoping import get_user_lab_units_in_hospital
    
    with get_db_session() as db:
        user_id = current_user.id
        hospital_id = current_user.hospital_id if current_user.has_role("local_admin") and not current_user.has_role("admin") else None

        # Admins get all assigned lab units; local_admin stays hospital-scoped.
        lab_unit_ids = get_user_lab_units_in_hospital(
            user_id=user_id,
            hospital_id=hospital_id,
            db=db
        )
        
        # Get the lab unit details from the database
        lab_units = db.query(LabUnit).filter(LabUnit.id.in_(list(lab_unit_ids))).all()
        
        # Format the results
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
            'user_id': user_id,
            'hospital_id': current_user.hospital_id if hospital_id is not None else None,
            'is_master_admin': current_user.is_master_admin,
            'eligible_lab_units': eligible_lab_units
        })
    

@api_bp.route("/eligibleLabUnitCurrentUser", methods=["GET"])
@login_required
@roles_required("admin", "local_admin", "data_manager", "ophthalmologist", "resident", "optometrist", "fileUploader")
def get_eligible_lab_units_currentUser():
    """API endpoint to get eligible lab units for the current user only (hospital-aware)."""
    from utils.hospital_scoping import get_user_lab_units_in_hospital
    
    with get_db_session() as db:
        # Always use the current user's ID, regardless of admin status
        user_id = current_user.id
        hospital_id = current_user.hospital_id if current_user.has_role("local_admin") and not current_user.has_role("admin") else None
        
        # Admins get all assigned lab units; local_admin stays hospital-scoped.
        lab_unit_ids = get_user_lab_units_in_hospital(
            user_id=user_id,
            hospital_id=hospital_id,
            db=db
        )
        
        # Get the lab unit details from the database
        lab_units = db.query(LabUnit).filter(LabUnit.id.in_(list(lab_unit_ids))).all()
        
        # Get hospital details
        # Master admin sees all hospitals, regular users see only their hospital
        if current_user.has_role("admin"):
            hospitals = db.query(Hospital).order_by(Hospital.name).all()
        else:
            if current_user.hospital_id:
                hospitals = db.query(Hospital).filter_by(id=current_user.hospital_id).all()
            else:
                hospitals = []
        
        # Format the results
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
            'user_id': user_id,
            'hospital_id': current_user.hospital_id if hospital_id is not None else None,
            'is_master_admin': current_user.is_master_admin,
            'eligible_lab_units': eligible_lab_units,
            'eligible_hospitals': eligible_hospitals
        })
