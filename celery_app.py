"""
Celery application factory.

This module must not import Flask app or blueprints.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from celery import Celery
from celery.schedules import crontab

from utils.env_loader import load_environment

# Ensure project root is on sys.path for task discovery in containers
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _env_bool(key: str, default: str = "false") -> bool:
    return str(os.getenv(key, default)).lower() in ("1", "true", "yes")


def _parse_times(value: str) -> list[str]:
    if not value:
        return []
    return [t.strip() for t in value.split(",") if t.strip()]


def _times_to_crontab(times: list[str]) -> list[crontab]:
    schedules: list[crontab] = []
    for t in times:
        try:
            hour_str, minute_str = t.split(":")
            schedules.append(crontab(minute=int(minute_str), hour=int(hour_str)))
        except Exception:
            continue
    return schedules


def make_celery_app() -> Celery:
    load_environment()

    broker_url = os.getenv("CELERY_BROKER_URL")
    result_backend = os.getenv("CELERY_RESULT_BACKEND")

    app = Celery(
        "fundus_img_xtract",
        broker=broker_url,
        backend=result_backend,
    )

    app.conf.update(
        task_default_queue="default",
        task_default_exchange="default",
        task_default_routing_key="default",
        task_track_started=_env_bool("CELERY_TASK_TRACK_STARTED", "true"),
        task_time_limit=int(os.getenv("CELERY_TASK_TIME_LIMIT", "3600")),
        task_soft_time_limit=int(os.getenv("CELERY_TASK_SOFT_TIME_LIMIT", "3300")),
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone=os.getenv("CELERY_TIMEZONE", "UTC"),
        enable_utc=True,
        task_routes={
            "celery_tasks.tasks.pii_tasks.*": {"queue": "pii_detection"},
            "celery_tasks.tasks.ocr_tasks.*": {"queue": "zip_ocr"},
            "celery_tasks.tasks.zip_tasks.*": {"queue": "zip_ocr"},
            "celery_tasks.tasks.thumbnail_tasks.*": {"queue": "thumbnails"},
            "celery_tasks.tasks.metadata_tasks.*": {"queue": "metadata"},
            "celery_tasks.tasks.task_backfill_tasks.*": {"queue": "maintenance"},
            "celery_tasks.tasks.export_tasks.*": {"queue": "exports"},
            "celery_tasks.tasks.maintenance_tasks.*": {"queue": "maintenance"},
            "celery_tasks.tasks.s3_tasks.*": {"queue": "s3_sync"},
            # New Async Upload Routes
            "celery_tasks.tasks.zip_upload_tasks.process_zip_coordinator_task": {"queue": "zip_ocr"},
            "celery_tasks.tasks.zip_upload_tasks.process_image_thumbnail_task": {"queue": "thumbnails"},
            "celery_tasks.tasks.zip_upload_tasks.process_pdf_ocr_task": {"queue": "zip_ocr"},
            "celery_tasks.tasks.zip_upload_tasks.process_zip_data_combined_task": {"queue": "pii_detection"},
            # Direct Upload Routes
            "celery_tasks.tasks.direct_upload_tasks.process_direct_upload_thumbnail_task": {"queue": "thumbnails"},
            "celery_tasks.tasks.direct_upload_tasks.process_direct_data_combined_task": {"queue": "pii_detection"},
            "celery_tasks.tasks.direct_upload_tasks.process_direct_metadata_only_task": {"queue": "metadata"},
            "celery_tasks.tasks.direct_upload_tasks.process_direct_pii_only_task": {"queue": "pii_detection"},
        },
    )

    app.autodiscover_tasks(["celery_tasks"], related_name="tasks")

    if _env_bool("CELERY_BEAT_USE_DB_SCHEDULES", "true"):
        app.conf.beat_scheduler = "celery_tasks.beat_scheduler.DatabaseScheduleScheduler"

    if _env_bool("CELERY_BEAT_ENABLED", "true"):
        beat_schedule = {
            "auto-rotate-peppers-hourly": {
                "task": "celery_tasks.tasks.maintenance_tasks.auto_rotate_peppers_task",
                "schedule": crontab(minute=0, hour="*"),
            },
        }

        mv_times = _parse_times(os.getenv("MATERIALIZED_VIEW_SCHEDULE_TIMES", ""))
        for idx, schedule in enumerate(_times_to_crontab(mv_times)):
            beat_schedule[f"materialized-view-refresh-{idx}"] = {
                "task": "celery_tasks.tasks.maintenance_tasks.refresh_materialized_views_task",
                "schedule": schedule,
            }

        thumb_times = _parse_times(os.getenv("THUMBNAIL_MAINTENANCE_SCHEDULE_TIMES", ""))
        for idx, schedule in enumerate(_times_to_crontab(thumb_times)):
            beat_schedule[f"thumbnail-maintenance-{idx}"] = {
                "task": "celery_tasks.tasks.maintenance_tasks.run_thumbnail_maintenance_task",
                "schedule": schedule,
            }

        # Package update scan - daily at 3 AM UTC
        beat_schedule["package-update-scan-daily"] = {
            "task": "celery_tasks.tasks.package_update_tasks.run_package_update_scan_task",
            "schedule": crontab(minute=0, hour="3"),
        }

        # Cleanup old package scans - daily at 4 AM UTC
        beat_schedule["package-update-cleanup-daily"] = {
            "task": "celery_tasks.tasks.package_update_tasks.cleanup_old_package_scans_task",
            "schedule": crontab(minute=0, hour="4"),
        }

        app.conf.beat_schedule = beat_schedule

    return app


celery_app = make_celery_app()
