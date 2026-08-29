from __future__ import annotations

import json

from flask import current_app, flash, redirect, render_template, request, url_for
from flask_login import login_required, current_user
from auth.roles import roles_required

from db_transaction_manager import get_db_session
from models import TaskBackfillJob
from utils.hospital_scoping import get_user_lab_units_in_hospital
from utils.task_backfill import (
    enqueue_task_backfill,
    get_missing_task_counts,
)


@login_required
@roles_required("admin")
def task_backfill_admin():
    with get_db_session() as db:
        hospital_id = current_user.hospital_id if current_user.has_role("local_admin") and not current_user.has_role("admin") else None
        allowed_lab_unit_ids = get_user_lab_units_in_hospital(
            current_user.id,
            hospital_id=hospital_id,
            db=db,
        )
        if not allowed_lab_unit_ids:
            flash("No assigned lab units found for this account.", "warning")

        totals = get_missing_task_counts(db, allowed_lab_unit_ids=allowed_lab_unit_ids)
        jobs_query = db.query(TaskBackfillJob).order_by(TaskBackfillJob.created_at.desc())
        if current_user.has_role("local_admin") and not current_user.has_role("admin"):
            if current_user.hospital_id:
                jobs_query = jobs_query.filter(TaskBackfillJob.hospital_id == current_user.hospital_id)
            else:
                jobs_query = jobs_query.filter(TaskBackfillJob.created_by_id == current_user.id)
        jobs = [
            {
                "id": job.id,
                "status": job.status,
                "created_at": job.created_at,
                "started_at": job.started_at,
                "finished_at": job.finished_at,
                "processed_count": job.processed_count,
                "total_candidates": job.total_candidates,
                "created_count": job.created_count,
                "error_count": job.error_count,
                "requested_limit": job.requested_limit,
                "created_by_username": job.created_by_username,
                "created_by_id": job.created_by_id,
                "hospital_id": job.hospital_id,
            }
            for job in jobs_query.limit(50).all()
        ]

    return render_template("admin/task_backfill.html", totals=totals, jobs=jobs)


@login_required
@roles_required("admin")
def task_backfill_run():
    limit = request.form.get("limit", type=int)

    with get_db_session() as db:
        hospital_id = current_user.hospital_id if current_user.has_role("local_admin") and not current_user.has_role("admin") else None
        allowed_lab_unit_ids = get_user_lab_units_in_hospital(
            current_user.id,
            hospital_id=hospital_id,
            db=db,
        )
        if not allowed_lab_unit_ids:
            flash("No assigned lab units found for this account.", "danger")
            return redirect(url_for("admin.task_backfill_admin"))

        active_job = (
            db.query(TaskBackfillJob)
            .filter(TaskBackfillJob.status.in_(["queued", "running"]))
            .first()
        )
        if active_job:
            flash("Another task backfill job is already running.", "warning")
            return redirect(url_for("admin.task_backfill_admin"))

        job = TaskBackfillJob(
            status="queued",
            requested_limit=limit,
            created_by_id=current_user.id,
            created_by_username=getattr(current_user, "username", None),
            hospital_id=hospital_id,
            allowed_lab_unit_ids=json.dumps(sorted(allowed_lab_unit_ids)),
        )
        db.add(job)
        db.commit()
        job_id = job.id

    enqueue_task_backfill(
        current_app._get_current_object(),
        job_id,
        user_id=current_user.id,
        hospital_id=hospital_id,
    )
    flash("Task backfill queued.", "info")
    return redirect(url_for("admin.task_backfill_admin"))
