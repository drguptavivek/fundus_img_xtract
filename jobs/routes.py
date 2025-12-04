# jobs/routes.py
from flask import flash, jsonify, redirect, render_template, url_for
from flask_login import login_required, current_user
from auth.roles import roles_required
from job_store import db_get_job_payload
from sqlalchemy.orm import selectinload
from sqlalchemy import select
from models import Job, JobItem, LabUnit
from db_transaction_manager import get_db_session
from utils.upload_eligibility import get_user_lab_unit_ids_no_admin_override
from review.discrepancy_export import EXPORT_DIR

from . import jobs_bp

@jobs_bp.route("/", methods=["GET"])
@login_required
@roles_required("admin", "local_admin", "fileUploader", "optometrist", "data_manager")
def list_recent_jobs():
    from flask import request
    
    with get_db_session() as db:
        allowed_lab_units = get_user_lab_unit_ids_no_admin_override(current_user.id)

        # Get filter and pagination parameters
        job_type_filter = request.args.get('job_type', '')
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        
        # Limit per_page to reasonable values
        per_page = min(max(per_page, 10), 100)
        
        # Build the base query: show jobs in allowed labs OR created by the user OR lab_unit_id is NULL
        visibility_filter = (
            (Job.lab_unit_id.in_(allowed_lab_units)) |
            (Job.lab_unit_id.is_(None)) |
            (Job.uploader_user_id == current_user.id)
        )
        query = (
            db.query(Job)
            .options(selectinload(Job.lab_unit).selectinload(LabUnit.hospital))
            .filter(visibility_filter)
        )
        
        # Apply job type filter if specified
        if job_type_filter:
            query = query.filter(Job.upload_type == job_type_filter)
        
        # Get total count for pagination
        total_count = query.count()
        
        # Calculate pagination values
        total_pages = (total_count + per_page - 1) // per_page
        offset = (page - 1) * per_page
        
        # Execute query with ordering, offset and limit
        jobs = (
            query
            .order_by(Job.created_at.desc())
            .offset(offset)
            .limit(per_page)
            .all()
        )
        
        # Get all unique job types for the filter dropdown
        job_types = (
            db.query(Job.upload_type)
            .filter(Job.upload_type.isnot(None))
            .distinct()
            .all()
        )
        job_types = [jt[0] for jt in job_types]
        
        # Compute counts per job
        rejections = {}
        totals = {}
        successes = {}
        for j in jobs:
            # Count rejected items
            error_cnt = (
                db.query(JobItem)
                .filter(JobItem.job_id == j.id)
                .filter(JobItem.state == "error")
                .count()
            )
            rejections[j.id] = error_cnt
            
            # Count total items
            total_cnt = (
                db.query(JobItem)
                .filter(JobItem.job_id == j.id)
                .count()
            )
            totals[j.id] = total_cnt
            
            # Count successful items (completed state)
            success_cnt = (
                db.query(JobItem)
                .filter(JobItem.job_id == j.id)
                .filter(JobItem.state == "completed")
                .count()
            )
            successes[j.id] = success_cnt
            
        # Build pagination info
        pagination = {
            'page': page,
            'per_page': per_page,
            'total_count': total_count,
            'total_pages': total_pages,
            'has_prev': page > 1,
            'has_next': page < total_pages,
            'prev_num': page - 1 if page > 1 else None,
            'next_num': page + 1 if page < total_pages else None,
        }
            
        return render_template(
            "jobs/jobs_list.html",
            jobs=jobs,
            rejections=rejections,
            totals=totals,
            successes=successes,
            job_types=job_types,
            selected_job_type=job_type_filter,
            pagination=pagination
        )



@jobs_bp.route("/<job_token>", methods=["GET"])
@login_required
@roles_required("admin", "local_admin", "fileUploader", "optometrist", "data_manager")
def job_status_json(job_token: str):
    with get_db_session() as db:
        job = db.query(Job).filter(Job.token == job_token).first()
        if not job:
            return jsonify({"error": "job not found"}), 404
        allowed_lab_units = get_user_lab_unit_ids_no_admin_override(current_user.id)
        if job.lab_unit_id not in allowed_lab_units and job.lab_unit_id is not None and job.uploader_user_id != current_user.id:
            return jsonify({"error": "job not found"}), 404
        
        payload = db_get_job_payload(job_token)
        if not payload:
            return jsonify({"error": "job not found"}), 404
            
        # Add upload_type to the payload
        payload["upload_type"] = job.upload_type
        if job.upload_type == "discrepancy_export":
            payload["export_files"] = _list_export_files(job.token)
            payload["download_base"] = url_for("review.discrepancy_export_download", job_token=job.token, filename="", _external=True)
        return jsonify(payload)

@jobs_bp.route("/<job_token>/view", methods=["GET"])
@login_required
@roles_required("admin", "local_admin", "fileUploader", "optometrist", "data_manager")
def job_status_page(job_token: str):
    # simple HTML page that polls <token> JSON
    return render_template("jobs/job_status.html", job_id=job_token)

@jobs_bp.route("/results/details/<job_token>", methods=["GET"])
@login_required
@roles_required("admin", "local_admin", "fileUploader", "optometrist", "data_manager")
def upload_results(job_token):
    with get_db_session() as db:
        job = db.query(Job).filter_by(token=job_token).first()
        if not job:
            flash("Upload job not found or unauthorized access.", "danger")
            return redirect(url_for("direct_uploads.upload"))

        allowed_lab_units = get_user_lab_unit_ids_no_admin_override(current_user.id)
        if job.lab_unit_id not in allowed_lab_units and job.uploader_user_id != current_user.id:
            flash("Upload job not found or unauthorized access.", "danger")
            return redirect(url_for("direct_uploads.upload"))

        items = db.execute(select(JobItem).where(JobItem.job_id == job.id).order_by(JobItem.id)).scalars().all()
        uploaded = sum(1 for it in items if it.state == "completed")
        failed   = len(items) - uploaded
        failures = [{"filename": it.filename, "reason": it.detail} for it in items if it.state == "error"]
        return render_template("jobs/upload_results.html",
                               results={"uploaded_count": uploaded, "failed_count": failed, "failed_uploads": failures},
                               job=job)

@jobs_bp.route("/processing/<job_id>", methods=["GET"])
@login_required
@roles_required("admin", "local_admin", "fileUploader", "optometrist", "data_manager")
def upload_processing(job_id):
    return render_template("jobs/jobs_processing.html", job_id=job_id)


def _list_export_files(job_token: str) -> list[str]:
    export_dir = (EXPORT_DIR / job_token).resolve()
    if not export_dir.exists() or not export_dir.is_dir():
        return []
    try:
        files = [p.name for p in export_dir.iterdir() if p.is_file()]
        return sorted(files)
    except Exception:
        return []
