from flask import render_template, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import select
from . import bp
from .utils import with_session
from auth.roles import roles_required
from models import Job, JobItem

@bp.route("/direct/upload/results/<int:job_id>", methods=["GET"])
@roles_required('contributor', 'data_manager', 'admin')
def upload_results(job_id):
    with with_session() as db:
        job = db.get(Job, job_id)
        if not job or job.uploader_user_id != current_user.id:
            flash("Upload job not found or unauthorized access.", "danger")
            return redirect(url_for("direct_uploads.upload"))

        items = db.execute(select(JobItem).where(JobItem.job_id == job_id).order_by(JobItem.id)).scalars().all()
        uploaded = sum(1 for it in items if it.state == "completed")
        failed   = len(items) - uploaded
        failures = [{"filename": it.filename, "reason": it.detail} for it in items if it.state == "error"]
        return render_template("direct_uploads/upload_results.html",
                               results={"uploaded_count": uploaded, "failed_count": failed, "failed_uploads": failures},
                               job=job)

@bp.route("/api/direct/upload/status/<int:job_id>", methods=["GET"])
@login_required
def api_upload_status(job_id):
    with with_session() as db:
        job = db.get(Job, job_id)
        if not job or job.uploader_user_id != current_user.id:
            return jsonify({"error": "Upload job not found or unauthorized access."}), 404

        items = db.execute(select(JobItem).where(JobItem.job_id == job_id).order_by(JobItem.id)).scalars().all()
        payload = [{"filename": it.filename, "state": it.state, "detail": it.detail} for it in items]
        return jsonify({"job_id": job_id, "job_status": job.status, "items": payload})
