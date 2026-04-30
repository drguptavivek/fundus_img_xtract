# api/direct_uploads.py
from flask import jsonify, request
from flask_login import login_required, current_user
from sqlalchemy import select

from db_transaction_manager import get_db_session

# Import the blueprint
from . import api_bp

# Import utility functions and models
from auth.roles import roles_required
from models import User, LabUnit, Job, JobItem
from utils.upload_eligibility import get_user_lab_unit_ids_no_admin_override
from utils.hospital_scoping import apply_scoping


# -------------------
# Direct Uploads API
# -------------------

@api_bp.route('/users/<int:user_id>/lab-units', methods=['GET'])
@login_required
@roles_required("fileUploader")
def get_lab_units(user_id):
    """Get lab units for a user."""
    with get_db_session() as db:
        user = db.get(User, user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404
        if current_user.id != user_id:
            return jsonify({"error": "Forbidden"}), 403

        query = select(LabUnit).order_by(LabUnit.name.asc())
        query = apply_scoping(query, LabUnit, current_user, "view")
        lab_units = db.execute(query).scalars().all()
        
        return jsonify([{"id": lu.id, "name": lu.name} for lu in lab_units])


@api_bp.route('/lab-units/<int:lab_unit_id>/hospital', methods=['GET'])
@login_required
@roles_required("fileUploader")
def get_hospital(lab_unit_id):
    """Get hospital for a lab unit."""
    with get_db_session() as db:
        query = select(LabUnit).where(LabUnit.id == lab_unit_id).options(selectinload(LabUnit.hospital))
        query = apply_scoping(query, LabUnit, current_user, "view")
        lu = db.execute(query).scalar_one_or_none()
        
        if not lu:
            return jsonify({"error": "Lab unit not found or access denied"}), 404
        return jsonify({"id": lu.hospital.id, "name": lu.hospital.name})


@api_bp.route('/upload-jobs/<job_token>/status', methods=['GET'])
@login_required
@roles_required("fileUploader")
def get_upload_status(job_token):
    """Get status of a direct upload job."""
    with get_db_session() as db:
        job = db.query(Job).filter_by(token=job_token).first()
        # Scope check: Job must belong to user or be in user's scoped lab units
        if not job:
             return jsonify({"error": "Upload job not found."}), 404
             
        if job.uploader_user_id != current_user.id:
            # Check if it belongs to valid lab units (if uploader is different)
            allowed_lab_unit_ids = get_user_lab_unit_ids_no_admin_override(current_user.id)
            if job.lab_unit_id not in allowed_lab_unit_ids:
                return jsonify({"error": "Unauthorized access to this job."}), 403

        items = db.execute(select(JobItem).where(JobItem.job_id == job.id).order_by(JobItem.id)).scalars().all()
        payload = [{"filename": it.filename, "state": it.state, "detail": it.detail} for it in items]
        return jsonify({"job_id": job.id, "job_token": job.token, "job_status": job.status, "items": payload})
