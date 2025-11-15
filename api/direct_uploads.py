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


# -------------------
# Direct Uploads API
# -------------------

@api_bp.route('/users/<int:user_id>/lab-units', methods=['GET'])
@login_required
def get_lab_units(user_id):
    """Get lab units for a user."""
    with get_db_session() as db:
        user = db.get(User, user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404
        if not (current_user.has_role('admin', 'data_manager') or current_user.id == user_id):
            return jsonify({"error": "Forbidden"}), 403
        return jsonify([{"id": lu.id, "name": lu.name} for lu in user.lab_units])


@api_bp.route('/lab-units/<int:lab_unit_id>/hospital', methods=['GET'])
@login_required
def get_hospital(lab_unit_id):
    """Get hospital for a lab unit."""
    with get_db_session() as db:
        lu = db.get(LabUnit, lab_unit_id)
        if not lu:
            return jsonify({"error": "Lab unit not found"}), 404
        return jsonify({"id": lu.hospital.id, "name": lu.hospital.name})


@api_bp.route('/upload-jobs/<job_token>/status', methods=['GET'])
@login_required
def get_upload_status(job_token):
    """Get status of a direct upload job."""
    with get_db_session() as db:
        job = db.query(Job).filter_by(token=job_token).first()
        if not job or job.uploader_user_id != current_user.id:
            return jsonify({"error": "Upload job not found or unauthorized access."}), 404

        items = db.execute(select(JobItem).where(JobItem.job_id == job.id).order_by(JobItem.id)).scalars().all()
        payload = [{"filename": it.filename, "state": it.state, "detail": it.detail} for it in items]
        return jsonify({"job_id": job.id, "job_token": job.token, "job_status": job.status, "items": payload})