# jobs/routes.py
from flask import jsonify, render_template
from flask import current_app
from flask import request
from . import bp
from job_store import db_get_job_payload
from models import Session, Job  # <-- add this import


@bp.route("/jobs/<job_token>", methods=["GET"])
def job_status_json(job_token: str):
    payload = db_get_job_payload(job_token)
    if not payload:
        return jsonify({"error": "job not found"}), 404
    return jsonify(payload)

@bp.route("/jobs/<job_token>/view", methods=["GET"])
def job_status_page(job_token: str):
    # simple HTML page that polls /jobs/<token> JSON
    return render_template("job_status.html", job_id=job_token)

# ---------------- NEW: health check ----------------
@bp.route("/healthz", methods=["GET"])
def healthz():
    db = Session()
    try:
        total = db.query(Job).count()
        queued = db.query(Job).filter(Job.status == "queued").count()
        processing = db.query(Job).filter(Job.status == "processing").count()
        errors = db.query(Job).filter(Job.status == "error").count()
        return jsonify({
            "status": "ok",
            "workers": current_app.config.get("WORKERS", None),
            "jobs": {
                "total": total,
                "queued": queued,
                "processing": processing,
                "error": errors,
            }
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        db.close()

# ---------------- NEW: recent jobs list (admin-lite) ----------------
@bp.route("/jobs", methods=["GET"])
def list_recent_jobs():
    db = Session()
    try:
        jobs = (
            db.query(Job)
            .order_by(Job.created_at.desc())
            .limit(100)
            .all()
        )
        return render_template("jobs_list.html", jobs=jobs)
    finally:
        db.close()
