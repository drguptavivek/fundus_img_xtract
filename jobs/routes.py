# jobs/routes.py
from flask import jsonify, render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from auth.roles import roles_required
from job_store import db_get_job_payload
from sqlalchemy.orm import selectinload
from sqlalchemy import select
from models import Session, Job, JobItem, LabUnit


from . import jobs_bp

@jobs_bp.route("/", methods=["GET"])
def list_recent_jobs():
    from flask import request
    
    db = Session()
    try:
        # Get filter and pagination parameters
        job_type_filter = request.args.get('job_type', '')
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        
        # Limit per_page to reasonable values
        per_page = min(max(per_page, 10), 100)
        
        # Build the base query
        query = (
            db.query(Job)
            .options(selectinload(Job.lab_unit).selectinload(LabUnit.hospital))
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
    finally:
        db.close()



@jobs_bp.route("/<job_token>", methods=["GET"])
@roles_required("admin", "fileUploader", "optometrist", "data_manager")
def job_status_json(job_token: str):
    db = Session()
    try:
        job = db.query(Job).filter(Job.token == job_token).first()
        if not job:
            return jsonify({"error": "job not found"}), 404
        
        payload = db_get_job_payload(job_token)
        if not payload:
            return jsonify({"error": "job not found"}), 404
            
        # Add upload_type to the payload
        payload["upload_type"] = job.upload_type
        return jsonify(payload)
    finally:
        db.close()

@jobs_bp.route("/<job_token>/view", methods=["GET"])
@roles_required("admin", "fileUploader", "optometrist", "data_manager")
def job_status_page(job_token: str):
    # simple HTML page that polls <token> JSON
    return render_template("jobs/job_status.html", job_id=job_token)

@jobs_bp.route("/results/details/<job_token>", methods=["GET"])
@roles_required('fileUploader', 'optometrist', 'data_manager', 'admin')
def upload_results(job_token):
    db = Session()
    try:
        job = db.query(Job).filter_by(token=job_token).first()
        if not job or (job.uploader_user_id != current_user.id and not current_user.has_role('admin', 'data_manager')):
            flash("Upload job not found or unauthorized access.", "danger")
            return redirect(url_for("direct_uploads.upload"))

        items = db.execute(select(JobItem).where(JobItem.job_id == job.id).order_by(JobItem.id)).scalars().all()
        uploaded = sum(1 for it in items if it.state == "completed")
        failed   = len(items) - uploaded
        failures = [{"filename": it.filename, "reason": it.detail} for it in items if it.state == "error"]
        return render_template("jobs/upload_results.html",
                               results={"uploaded_count": uploaded, "failed_count": failed, "failed_uploads": failures},
                               job=job)
    finally:
        db.close()

@jobs_bp.route("/processing/<job_id>", methods=["GET"])
@roles_required('fileUploader', 'optometrist', 'data_manager', 'admin')
def upload_processing(job_id):
    return render_template("jobs/jobs_processing.html", job_id=job_id)
