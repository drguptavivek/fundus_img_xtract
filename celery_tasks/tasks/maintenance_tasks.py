from __future__ import annotations

from celery_app import celery_app
from utils.celery_context import build_task_app
from utils.materialized_view_scheduler import refresh_materialized_view
from utils.thumbnail_maintenance_scheduler import (
    cleanup_orphaned_thumbnails,
    regenerate_missing_thumbnails,
    validate_thumbnail_integrity,
    run_maintenance_tasks,
)
# Lazy import to avoid loading S3/nacl in beat container
# from utils.s3_url_signing import auto_rotate_peppers


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
