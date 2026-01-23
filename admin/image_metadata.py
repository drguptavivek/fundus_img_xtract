import json
from datetime import timedelta

from flask import current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import login_required, current_user
from auth.roles import roles_required
from auth.utils import utcnow
from app_cache import cache
from db_transaction_manager import get_db_session
from models import ImageMetadataBackfillJob, PiiDetectionJob
from utils.hospital_scoping import get_user_lab_units_in_hospital
from utils.image_metadata_backfill import (
    enqueue_image_metadata_backfill,
    get_missing_pii_counts,
    get_missing_metadata_counts,
    get_pii_assessed_counts,
    get_total_image_counts,
)
from utils.pii_detection_queue import run_pii_detection_queue



@login_required
@roles_required("admin", "local_admin")
def image_metadata_admin():
    with get_db_session() as db:
        allowed_lab_unit_ids = get_user_lab_units_in_hospital(
            current_user.id,
            hospital_id=current_user.hospital_id,
            db=db,
        )
        if not allowed_lab_unit_ids:
            flash("No assigned lab units found for this account.", "warning")

        allowed_lab_unit_ids_tuple = tuple(sorted(allowed_lab_unit_ids))
        totals, pii_totals, total_images, pii_assessed = _get_status_counts_cached(allowed_lab_unit_ids_tuple)
    return render_template(
        "admin/image_metadata.html",
        totals=totals,
        pii_totals=pii_totals,
        total_images=total_images,
        pii_assessed=pii_assessed,
        jobs=[],
        pii_counts={},
        pii_recent=[],
        pii_page=1,
        pii_has_prev=False,
        pii_has_next=False,
    )


@login_required
@roles_required("admin", "local_admin")
def image_metadata_backfill():
    limit = request.form.get("limit", type=int)
    mode = (request.form.get("mode") or "both").strip().lower()
    run_metadata = mode in {"both", "metadata"}
    run_pii = mode in {"both", "pii"}
    if not run_metadata and not run_pii:
        flash("Select a valid backfill mode.", "danger")
        return redirect(url_for("admin.image_metadata_admin"))
    with get_db_session() as db:
        allowed_lab_unit_ids = get_user_lab_units_in_hospital(
            current_user.id,
            hospital_id=current_user.hospital_id,
            db=db,
        )
        if not allowed_lab_unit_ids:
            flash("No assigned lab units found for this account.", "danger")
            return redirect(url_for("admin.image_metadata_admin"))

        active_job = (
            db.query(ImageMetadataBackfillJob)
            .filter(ImageMetadataBackfillJob.status.in_(["queued", "running"]))
            .first()
        )
        if active_job:
            flash("Another metadata backfill job is already running.", "warning")
            return redirect(url_for("admin.image_metadata_admin"))

        job = ImageMetadataBackfillJob(
            status="queued",
            requested_limit=limit,
            run_metadata=run_metadata,
            run_pii=run_pii,
            created_by_id=current_user.id,
            created_by_username=getattr(current_user, "username", None),
            hospital_id=current_user.hospital_id,
            allowed_lab_unit_ids=json.dumps(sorted(allowed_lab_unit_ids)),
        )
        db.add(job)
        db.commit()
        job_id = job.id

    enqueue_image_metadata_backfill(current_app._get_current_object(), job_id)
    mode_label = "metadata" if run_metadata and not run_pii else "PII" if run_pii and not run_metadata else "metadata + PII"
    flash(f"Image backfill queued ({mode_label}).", "info")
    return redirect(url_for("admin.image_metadata_admin"))


@login_required
@roles_required("admin", "local_admin")
def image_metadata_status():
    cache_key = f"image_metadata_status:{current_user.hospital_id}:{current_user.id}"
    cached = cache.get(cache_key)
    if isinstance(cached, dict):
        return jsonify(cached)

    with get_db_session() as db:
        allowed_lab_unit_ids = get_user_lab_units_in_hospital(
            current_user.id,
            hospital_id=current_user.hospital_id,
            db=db,
        )
        allowed_lab_unit_ids_tuple = tuple(sorted(allowed_lab_unit_ids))
        totals, pii_totals, total_images, pii_assessed = _get_status_counts_cached(allowed_lab_unit_ids_tuple)
        active_job = (
            db.query(ImageMetadataBackfillJob)
            .filter(ImageMetadataBackfillJob.status.in_(["queued", "running"]))
            .order_by(ImageMetadataBackfillJob.created_at.desc())
            .first()
        )
        active_payload = None
        if active_job:
            active_payload = {
                "id": active_job.id,
                "status": active_job.status,
                "processed_count": active_job.processed_count,
                "total_candidates": active_job.total_candidates,
                "metadata_created_count": active_job.metadata_created_count,
                "pii_created_count": active_job.pii_created_count,
                "error_count": active_job.error_count,
                "run_metadata": active_job.run_metadata,
                "run_pii": active_job.run_pii,
                "started_at": active_job.started_at.isoformat() if active_job.started_at else None,
            }

    payload = {
        "metadata_missing": totals,
        "pii_missing": pii_totals,
        "metadata_present": {
            "encounter": max(0, total_images["encounter"] - totals["encounter"]),
            "direct": max(0, total_images["direct"] - totals["direct"]),
            "direct_edited": max(0, total_images["direct_edited"] - totals["direct_edited"]),
        },
        "pii_present": {
            "encounter": max(0, total_images["encounter"] - pii_totals["encounter"]),
            "direct": max(0, total_images["direct"] - pii_totals["direct"]),
            "direct_edited": max(0, total_images["direct_edited"] - pii_totals["direct_edited"]),
        },
        "pii_assessed": pii_assessed,
        "pii_processed": _get_pii_processed_counts(),
        "active_job": active_payload,
    }
    cache.set(cache_key, payload, timeout=60)
    return jsonify(payload)


@login_required
@roles_required("admin", "local_admin")
@cache.memoize(timeout=15)
def _get_status_counts_cached(allowed_lab_unit_ids: tuple[int, ...]):
    with get_db_session() as db:
        allowed_set = set(allowed_lab_unit_ids)
        totals = get_missing_metadata_counts(db, allowed_lab_unit_ids=allowed_set)
        pii_totals = get_missing_pii_counts(db, allowed_lab_unit_ids=allowed_set)
        total_images = get_total_image_counts(db, allowed_lab_unit_ids=allowed_set)
        pii_assessed = get_pii_assessed_counts(db, allowed_lab_unit_ids=allowed_set)
    return totals, pii_totals, total_images, pii_assessed


@cache.memoize(timeout=20)
def _get_pii_processed_counts():
    now = utcnow()
    hour_cutoff = now - timedelta(hours=1)
    day_cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0)
    with get_db_session() as db:
        processed_hour = (
            db.query(PiiDetectionJob.id)
            .filter(
                PiiDetectionJob.status == "completed",
                PiiDetectionJob.finished_at.isnot(None),
                PiiDetectionJob.finished_at >= hour_cutoff,
            )
            .count()
        )
        processed_day = (
            db.query(PiiDetectionJob.id)
            .filter(
                PiiDetectionJob.status == "completed",
                PiiDetectionJob.finished_at.isnot(None),
                PiiDetectionJob.finished_at >= day_cutoff,
            )
            .count()
        )
    return {"last_60_min": processed_hour, "today": processed_day}


@login_required
@roles_required("admin", "local_admin")
def image_metadata_run_pii_queue():
    limit = request.form.get("limit", type=int)
    processed = run_pii_detection_queue(max_jobs=limit)
    flash(f"PII queue processed {processed} job(s).", "info")
    return redirect(url_for("admin.image_metadata_admin"))
