from __future__ import annotations

import logging
from datetime import timedelta

from celery_app import celery_app
from sqlalchemy import and_, or_
from utils.celery_context import build_task_app
from auth.utils import utcnow
from db_transaction_manager import transaction_scope
from models import ImageMetadataBackfillJob, PiiDetectionJob
from utils.log_sanitize import sanitize_log_value
from utils.materialized_view_scheduler import refresh_materialized_view
from utils.thumbnail_maintenance_scheduler import (
    cleanup_orphaned_thumbnails,
    regenerate_missing_thumbnails,
    validate_thumbnail_integrity,
    run_maintenance_tasks,
)
# Lazy import to avoid loading S3/nacl in beat container
# from utils.s3_url_signing import auto_rotate_peppers

_LOGGER = logging.getLogger("maintenance")


@celery_app.task(name="celery_tasks.tasks.maintenance_tasks.refresh_materialized_views_task", bind=True, acks_late=True)
def refresh_materialized_views_task(self, user_id: int | None = None, hospital_id: int | None = None) -> bool:
    app = build_task_app()
    return bool(refresh_materialized_view(app, schedule_time="celery_beat"))


@celery_app.task(name="celery_tasks.tasks.maintenance_tasks.run_thumbnail_maintenance_task", bind=True, acks_late=True)
def run_thumbnail_maintenance_task(self, user_id: int | None = None, hospital_id: int | None = None) -> None:
    app = build_task_app()
    run_maintenance_tasks(app)


@celery_app.task(name="celery_tasks.tasks.maintenance_tasks.cleanup_orphaned_thumbnails_task", bind=True, acks_late=True)
def cleanup_orphaned_thumbnails_task(self, user_id: int | None = None, hospital_id: int | None = None) -> dict:
    app = build_task_app()
    return cleanup_orphaned_thumbnails(app, schedule_time="celery_beat")


@celery_app.task(name="celery_tasks.tasks.maintenance_tasks.regenerate_missing_thumbnails_task", bind=True, acks_late=True)
def regenerate_missing_thumbnails_task(
    self,
    limit: int = 100,
    user_id: int | None = None,
    hospital_id: int | None = None,
) -> dict:
    app = build_task_app()
    return regenerate_missing_thumbnails(app, schedule_time="celery_beat", limit=limit)


@celery_app.task(name="celery_tasks.tasks.maintenance_tasks.validate_thumbnail_integrity_task", bind=True, acks_late=True)
def validate_thumbnail_integrity_task(
    self,
    sample_size: int = 100,
    user_id: int | None = None,
    hospital_id: int | None = None,
) -> dict:
    app = build_task_app()
    return validate_thumbnail_integrity(app, schedule_time="celery_beat", sample_size=sample_size)


@celery_app.task(name="celery_tasks.tasks.maintenance_tasks.auto_rotate_peppers_task", bind=True, acks_late=True)
def auto_rotate_peppers_task(self, user_id: int | None = None, hospital_id: int | None = None) -> dict:
    # Lazy import to avoid loading S3/nacl in beat container
    from utils.s3_url_signing import auto_rotate_peppers
    return auto_rotate_peppers()


@celery_app.task(name="celery_tasks.tasks.maintenance_tasks.cleanup_stuck_jobs_task", bind=True, acks_late=True)
def cleanup_stuck_jobs_task(
    self,
    max_age_minutes: int = 20,
    user_id: int | None = None,
    hospital_id: int | None = None,
) -> dict:
    _ = user_id, hospital_id
    cutoff = utcnow() - timedelta(minutes=max_age_minutes)
    results = {"backfill_failed": 0, "pii_failed": 0}
    with transaction_scope() as db:
        backfill_jobs = (
            db.query(ImageMetadataBackfillJob)
            .filter(ImageMetadataBackfillJob.status == "running")
            .filter(
                or_(
                    and_(
                        ImageMetadataBackfillJob.started_at.is_(None),
                        ImageMetadataBackfillJob.created_at < cutoff,
                    ),
                    ImageMetadataBackfillJob.started_at < cutoff,
                )
            )
            .all()
        )
        for job in backfill_jobs:
            job.status = "failed"
            job.error_message = "Timed out by maintenance"
            job.finished_at = utcnow()
            results["backfill_failed"] += 1

        pii_jobs = (
            db.query(PiiDetectionJob)
            .filter(PiiDetectionJob.status == "running")
            .filter(
                or_(
                    and_(
                        PiiDetectionJob.started_at.is_(None),
                        PiiDetectionJob.created_at < cutoff,
                    ),
                    PiiDetectionJob.started_at < cutoff,
                )
            )
            .all()
        )
        for job in pii_jobs:
            job.status = "failed"
            job.error_message = "Timed out by maintenance"
            job.finished_at = utcnow()
            results["pii_failed"] += 1

    _LOGGER.info(
        "Cleanup stuck jobs complete: backfill_failed=%s pii_failed=%s cutoff=%s",
        sanitize_log_value(results["backfill_failed"]),
        sanitize_log_value(results["pii_failed"]),
        sanitize_log_value(cutoff.isoformat()),
    )
    return results
