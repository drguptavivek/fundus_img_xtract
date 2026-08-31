from flask import render_template, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import select
from . import bp
from db_transaction_manager import get_db_session
from auth.roles import roles_required
from models import Job, JobItem
from utils.upload_eligibility import get_user_lab_unit_ids_no_admin_override
from jobs.access import job_visible_to_actor

@bp.route("/api/direct/upload/status/<job_token>", methods=["GET"])
@login_required
@roles_required("admin", "local_admin", "fileUploader", "optometrist", "data_manager")
def api_upload_status(job_token):
    with get_db_session() as db:
        job = db.query(Job).filter_by(token=job_token).first()
        if not job:
            return jsonify({"error": "Upload job not found or unauthorized access."}), 404

        allowed_lab_units = get_user_lab_unit_ids_no_admin_override(current_user.id)
        if not job_visible_to_actor(
            job,
            user_id=current_user.id,
            is_admin=current_user.has_role("admin"),
            allowed_lab_unit_ids=allowed_lab_units,
        ):
            return jsonify({"error": "Upload job not found or unauthorized access."}), 404

        items = db.execute(select(JobItem).where(JobItem.job_id == job.id).order_by(JobItem.id)).scalars().all()
        payload = [{"filename": it.filename, "state": it.state, "detail": it.detail} for it in items]
        return jsonify({"job_id": job.id, "job_token": job.token, "job_status": job.status, "items": payload})
