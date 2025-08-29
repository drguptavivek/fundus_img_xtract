# jobs/routes.py
from flask import jsonify, render_template
from flask import current_app
from flask import request
from auth.roles import roles_required
from job_store import db_get_job_payload
from models import Session, Job, JobItem  # <-- add this import


from . import jobs_bp

@jobs_bp.route("/", methods=["GET"])
def list_recent_jobs():
    db = Session()
    try:
        jobs = (
            db.query(Job)
            .order_by(Job.created_at.desc())
            .limit(100)
            .all()
        )
        # Compute rejected counts per job (any item with error state)
        rejections = {}
        for j in jobs:
            cnt = (
                db.query(JobItem)
                .filter(JobItem.job_id == j.id)
                .filter(JobItem.state == "error")
                .count()
            )
            rejections[j.id] = cnt
        return render_template("jobs/jobs_list.html", jobs=jobs, rejections=rejections)
    finally:
        db.close()



@jobs_bp.route("/<job_token>", methods=["GET"])
@roles_required("admin")
def job_status_json(job_token: str):
    payload = db_get_job_payload(job_token)
    if not payload:
        return jsonify({"error": "job not found"}), 404
    return jsonify(payload)

@jobs_bp.route("/<job_token>/view", methods=["GET"])
@roles_required("admin")
def job_status_page(job_token: str):
    # simple HTML page that polls <token> JSON
    return render_template("jobs/job_status.html", job_id=job_token)

