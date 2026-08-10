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
from utils.dualGradingStuckTaskCleanup import reset_stuck_tasks
from grading.workbench.service import expire_stale_sessions
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


@celery_app.task(
    name="celery_tasks.tasks.maintenance_tasks.regenerate_missing_thumbnails_fast_task",
    bind=True,
    acks_late=True,
)
def regenerate_missing_thumbnails_fast_task(
    self,
    user_id: int | None = None,
    hospital_id: int | None = None,
) -> dict:
    app = build_task_app()
    return regenerate_missing_thumbnails(app, schedule_time="celery_beat_fast", limit=200)


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


@celery_app.task(name="celery_tasks.tasks.maintenance_tasks.check_celery_queues_task", bind=True, acks_late=True)
def check_celery_queues_task(self, user_id: int | None = None, hospital_id: int | None = None) -> dict:
    _ = self, user_id, hospital_id
    app = build_task_app()
    with app.app_context():
        from utils.celery_queue_monitor import check_celery_queues_and_alert

        result = check_celery_queues_and_alert()
    _LOGGER.info(
        "Celery queue health check complete: status=%s issues=%s alert=%s",
        sanitize_log_value(result.get("status")),
        sanitize_log_value(len(result.get("issues") or [])),
        sanitize_log_value(result.get("alert")),
    )
    return result


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


@celery_app.task(name="celery_tasks.tasks.maintenance_tasks.reset_stuck_task_trackers_task", bind=True, acks_late=True)
def reset_stuck_task_trackers_task(
    self,
    stale_minutes: int = 60,
    user_id: int | None = None,
    hospital_id: int | None = None,
) -> dict:
    _ = self, user_id, hospital_id
    reset_count = int(reset_stuck_tasks(time_limit_minutes=stale_minutes))
    _LOGGER.info(
        "Reset stuck task trackers complete: stale_minutes=%s reset_count=%s",
        sanitize_log_value(stale_minutes),
        sanitize_log_value(reset_count),
    )
    return {"reset_count": reset_count, "stale_minutes": stale_minutes}


@celery_app.task(name="celery_tasks.tasks.maintenance_tasks.expire_grading_workbench_sessions_task", bind=True, acks_late=True)
def expire_grading_workbench_sessions_task(
    self,
    user_id: int | None = None,
    hospital_id: int | None = None,
) -> dict:
    _ = self, user_id, hospital_id
    with transaction_scope() as db:
        expired_count = expire_stale_sessions(db)
    _LOGGER.info(
        "Expired grading workbench sessions: count=%s",
        sanitize_log_value(expired_count),
    )
    return {"expired_count": expired_count}
