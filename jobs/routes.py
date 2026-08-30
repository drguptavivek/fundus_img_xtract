# jobs/routes.py
import json

from flask import abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import login_required, current_user
from auth.roles import roles_required
from job_store import db_create_job, db_get_job_payload
from sqlalchemy.orm import selectinload
from sqlalchemy import select
from models import CuratedDataset, CuratedDatasetItem, DatasetExport, Job, JobItem, LabUnit
from db_transaction_manager import get_db_session
from utils.upload_eligibility import get_user_lab_unit_ids_no_admin_override
from utils.rate_limiter import rate_limit
from review.discrepancy_export import EXPORT_DIR
from datasets.authorization import can_export_dataset

from . import jobs_bp
from .access import job_visible_to_actor, visible_jobs_predicate

def _current_user_can_see(job: Job, allowed_lab_units: set[int] | list[int]) -> bool:
    return job_visible_to_actor(
        job,
        user_id=current_user.id,
        is_admin=current_user.has_role("admin"),
        allowed_lab_unit_ids=allowed_lab_units or (),
    )


@jobs_bp.route("/", methods=["GET"])
@login_required
@roles_required("admin", "local_admin", "fileUploader", "optometrist", "data_manager", "discrepancy_reviewer", "data_exporter")
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
        visibility_filter = visible_jobs_predicate(
            user_id=current_user.id,
            is_admin=current_user.has_role("admin"),
            allowed_lab_unit_ids=allowed_lab_units,
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
            .filter(visibility_filter, Job.upload_type.isnot(None))
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
def job_status_json(job_token: str):
    with get_db_session() as db:
        job = db.query(Job).filter(Job.token == job_token).first()
        if not job:
            return jsonify({"error": "job not found"}), 404
        allowed_lab_units = get_user_lab_unit_ids_no_admin_override(current_user.id)
        if not _current_user_can_see(job, allowed_lab_units):
            return jsonify({"error": "job not found"}), 404
        
        payload = db_get_job_payload(job_token)
        if not payload:
            return jsonify({"error": "job not found"}), 404
            
        # Add upload_type to the payload
        payload["upload_type"] = job.upload_type
        if job.upload_type in ("discrepancy_export", "dataset_export"):
            payload["export_files"] = _list_export_files(job.token)
            download_endpoint = (
                "review.discrepancy_export_download"
                if job.upload_type == "discrepancy_export"
                else "analytics.dataset_export_download"
            )
            payload["download_base"] = url_for(download_endpoint, job_token=job.token, filename="", _external=True)
        if job.upload_type == "dataset_export":
            dataset_export = db.query(DatasetExport).filter(DatasetExport.job_id == job.id).first()
            if dataset_export and dataset_export.dataset:
                payload["dataset_name"] = dataset_export.dataset.name
                payload["dataset_uuid"] = dataset_export.dataset.uuid
                payload["dataset_detail_url"] = url_for(
                    "analytics.dataset_detail",
                    dataset_uuid=dataset_export.dataset.uuid,
                )
        return jsonify(payload)

@jobs_bp.route("/<job_token>/view", methods=["GET"])
@login_required
def job_status_page(job_token: str):
    with get_db_session() as db:
        job = db.query(Job).filter(Job.token == job_token).first()
        allowed_lab_units = get_user_lab_unit_ids_no_admin_override(current_user.id)
        if not job or not _current_user_can_see(job, allowed_lab_units):
            abort(404)
    if job and job.upload_type in ("discrepancy_export", "dataset_export"):
        return render_template("jobs/export_job_status.html", job_id=job_token)
    return render_template("jobs/job_status.html", job_id=job_token)


@jobs_bp.route("/<job_token>/regenerate", methods=["POST"])
@login_required
@rate_limit("1 per minute")
def regenerate_export(job_token: str):
    from flask import current_app
    from review.discrepancy_export import (
        enqueue_dataset_export,
        enqueue_discrepancy_export,
        reauthorize_discrepancy_filters,
    )

    with get_db_session() as db:
        job = db.query(Job).filter(Job.token == job_token).first()
        if not job or job.upload_type not in ("dataset_export", "discrepancy_export"):
            abort(404)

        allowed_lab_units = get_user_lab_unit_ids_no_admin_override(current_user.id)
        if not _current_user_can_see(job, allowed_lab_units):
            abort(404)

        xff = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
        ip = xff or (request.remote_addr or "-")
        uploader_username = getattr(current_user, "username", None)
        uploader_user_id = getattr(current_user, "id", None)

        if job.upload_type == "dataset_export":
            dataset_export = db.query(DatasetExport).filter(DatasetExport.job_id == job.id).first()
            if not dataset_export:
                flash("Dataset export metadata not found. Please re-export from the dataset page.", "warning")
                return redirect(url_for("jobs.job_status_page", job_token=job_token))

            dataset = (
                db.query(CuratedDataset)
                .filter(CuratedDataset.id == dataset_export.dataset_id, CuratedDataset.is_active.is_(True))
                .first()
            )
            if not dataset:
                flash("Dataset not found or inactive.", "warning")
                return redirect(url_for("jobs.job_status_page", job_token=job_token))
            # Owning the job token is not authority over the dataset.  Re-run
            # the same scoped export decision used by the dataset route.
            if not can_export_dataset(db, user=current_user, dataset=dataset):
                abort(404)
            if not dataset.is_finalized:
                flash("Finalize the dataset before exporting.", "warning")
                return redirect(url_for("analytics.dataset_detail", dataset_uuid=dataset.uuid))

            items = (
                db.query(CuratedDatasetItem)
                .filter(
                    CuratedDatasetItem.dataset_id == dataset.id,
                    CuratedDatasetItem.include_in_export.is_(True),
                )
                .all()
            )
            task_ids = [item.task_id for item in items]
            if not task_ids:
                flash("No tasks selected for export in this dataset.", "warning")
                return redirect(url_for("analytics.dataset_detail", dataset_uuid=dataset.uuid))

            stored_filters = {}
            try:
                stored_filters = json.loads(dataset.filters_json or "{}")
            except Exception:
                stored_filters = {}

            job_token = db_create_job(
                ["dataset_export"],
                [],
                uploader_user_id=uploader_user_id,
                uploader_username=uploader_username,
                uploader_ip=ip,
                upload_type="dataset_export",
            )
            job_record = db.query(Job).filter(Job.token == job_token).first()
            if job_record:
                db.add(
                    DatasetExport(
                        dataset_id=dataset.id,
                        job_id=job_record.id,
                        created_by_user_id=uploader_user_id,
                    )
                )
                db.flush()

            metadata = {
                "user_id": current_user.id,
                "dataset_name": dataset.name,
                "dataset_purpose": dataset.purpose,
                "disease_id": dataset.disease_id,
                **stored_filters,
            }
            enqueue_dataset_export(
                current_app._get_current_object(),
                job_token,
                dataset.id,
                task_ids,
                metadata,
            )
            flash("Dataset export regeneration queued.", "info")
            return redirect(url_for("jobs.job_status_page", job_token=job_token))

        filters_path = (EXPORT_DIR / job_token / "filters.json").resolve()
        if not filters_path.exists() or EXPORT_DIR not in filters_path.parents:
            flash("Export filters not found. Please re-export from the discrepancy review page.", "warning")
            return redirect(url_for("jobs.job_status_page", job_token=job_token))

        try:
            with filters_path.open("r", encoding="utf-8") as handle:
                filters = json.load(handle)
        except Exception:
            flash("Unable to read export filters. Please re-export from the discrepancy review page.", "warning")
            return redirect(url_for("jobs.job_status_page", job_token=job_token))

        try:
            filters = reauthorize_discrepancy_filters(db, current_user, filters)
        except (PermissionError, TypeError, ValueError):
            abort(404)
        lab_unit_id = filters.get("lab_unit_id")

        job_token = db_create_job(
            ["discrepancy_export"],
            [],
            uploader_user_id=uploader_user_id,
            uploader_username=uploader_username,
            uploader_ip=ip,
            lab_unit_id=lab_unit_id,
            upload_type="discrepancy_export",
        )
        enqueue_discrepancy_export(
            current_app._get_current_object(),
            job_token,
            filters,
            {"user_id": current_user.id},
        )
        flash("Discrepancy export regeneration queued.", "info")
        return redirect(url_for("jobs.job_status_page", job_token=job_token))

@jobs_bp.route("/results/details/<job_token>", methods=["GET"])
@login_required
@roles_required("admin", "local_admin", "fileUploader", "optometrist", "data_manager", "discrepancy_reviewer", "data_exporter")
def upload_results(job_token):
    with get_db_session() as db:
        job = db.query(Job).filter_by(token=job_token).first()
        if not job:
            flash("Upload job not found or unauthorized access.", "danger")
            return redirect(url_for("direct_uploads.upload"))

        allowed_lab_units = get_user_lab_unit_ids_no_admin_override(current_user.id)
        if not _current_user_can_see(job, allowed_lab_units):
            flash("Upload job not found or unauthorized access.", "danger")
            return redirect(url_for("direct_uploads.upload"))

        items = db.execute(select(JobItem).where(JobItem.job_id == job.id).order_by(JobItem.id)).scalars().all()
        uploaded = sum(1 for it in items if it.state in {"ok", "completed"})
        failed = sum(1 for it in items if it.state == "error")
        pending = len(items) - uploaded - failed
        failures = [{"filename": it.filename, "reason": it.detail} for it in items if it.state == "error"]
        return render_template("jobs/upload_results.html",
                               results={
                                   "uploaded_count": uploaded,
                                   "failed_count": failed,
                                   "pending_count": pending,
                                   "total_count": len(items),
                                   "failed_uploads": failures,
                               },
                               job=job)

@jobs_bp.route("/processing/<job_id>", methods=["GET"])
@login_required
@roles_required("admin", "local_admin", "fileUploader", "optometrist", "data_manager", "discrepancy_reviewer", "data_exporter")
def upload_processing(job_id):
    with get_db_session() as db:
        job = db.query(Job).filter(Job.token == job_id).first()
        allowed_lab_units = get_user_lab_unit_ids_no_admin_override(current_user.id)
        if not job or not _current_user_can_see(job, allowed_lab_units):
            abort(404)
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
