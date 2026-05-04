"""
Celery application factory.

This module must not import Flask app or blueprints.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from celery import Celery
from celery.schedules import crontab, schedule as celery_schedule

from utils.celery_queue_config import (
    CELERY_TASK_DEFAULT_EXCHANGE,
    CELERY_TASK_DEFAULT_QUEUE,
    CELERY_TASK_DEFAULT_ROUTING_KEY,
    CELERY_TASK_ROUTES,
)
from utils.env_loader import load_environment
from utils.redis_connection import build_redis_url

# Ensure project root is on sys.path for task discovery in containers
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _env_bool(key: str, default: str = "false") -> bool:
    return str(os.getenv(key, default)).lower() in ("1", "true", "yes")


def _env_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


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

    redis_url = build_redis_url()
    broker_url = os.getenv("CELERY_BROKER_URL") or redis_url
    result_backend = os.getenv("CELERY_RESULT_BACKEND") or redis_url

    app = Celery(
        "fundus_img_xtract",
        broker=broker_url,
        backend=result_backend,
    )

    app.conf.update(
        task_default_queue=CELERY_TASK_DEFAULT_QUEUE,
        task_default_exchange=CELERY_TASK_DEFAULT_EXCHANGE,
        task_default_routing_key=CELERY_TASK_DEFAULT_ROUTING_KEY,
        task_track_started=_env_bool("CELERY_TASK_TRACK_STARTED", "true"),
        task_time_limit=int(os.getenv("CELERY_TASK_TIME_LIMIT", "3600")),
        task_soft_time_limit=int(os.getenv("CELERY_TASK_SOFT_TIME_LIMIT", "3300")),
        broker_heartbeat=_env_int("CELERY_BROKER_HEARTBEAT", 60),
        broker_heartbeat_checkrate=_env_int("CELERY_BROKER_HEARTBEAT_CHECKRATE", 2),
        worker_heartbeat_interval=_env_int("CELERY_WORKER_HEARTBEAT_INTERVAL", 30),
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone=os.getenv("CELERY_TIMEZONE", "UTC"),
        enable_utc=True,
        task_routes=CELERY_TASK_ROUTES,
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

        queue_monitor_interval = _env_int("CELERY_QUEUE_MONITOR_INTERVAL_SECONDS", 300)
        beat_schedule["celery-queue-health-check"] = {
            "task": "celery_tasks.tasks.maintenance_tasks.check_celery_queues_task",
            "schedule": celery_schedule(max(60, queue_monitor_interval)),
        }

        # Package update scan - daily at 3 AM UTC
        beat_schedule["package-update-scan-daily"] = {
            "task": "celery_tasks.tasks.package_update_tasks.run_package_update_scan_task",
            "schedule": crontab(minute=0, hour="3"),
        }

        # Image listing v2 MVs - ensure creation daily at 2 AM UTC
        beat_schedule["mvw-image-listing-v2-ensure-daily"] = {
            "task": "celery_tasks.tasks.mv_tasks.ensure_image_listing_v2_task",
            "schedule": crontab(minute=0, hour="2"),
        }

        # Image listing v2 MVs - refresh every 30 minutes
        beat_schedule["mvw-image-listing-v2-refresh-30min"] = {
            "task": "celery_tasks.tasks.mv_tasks.refresh_image_listing_v2_task",
            "schedule": crontab(minute="0,30", hour="*"),
        }

        # Cleanup old package scans - daily at 4 AM UTC
        beat_schedule["package-update-cleanup-daily"] = {
            "task": "celery_tasks.tasks.package_update_tasks.cleanup_old_package_scans_task",
            "schedule": crontab(minute=0, hour="4"),
        }

        if not _env_bool("CELERY_BEAT_USE_DB_SCHEDULES", "true"):
            # Reset stale dual-grading task tracker locks when DB schedules are disabled.
            tracker_stale_minutes = _env_int("TASK_TRACKER_STALE_MINUTES", 60)
            tracker_reset_interval_minutes = _env_int("TASK_TRACKER_RESET_INTERVAL_MINUTES", 30)
            beat_schedule["task-tracker-reset-stale-locks"] = {
                "task": "celery_tasks.tasks.maintenance_tasks.reset_stuck_task_trackers_task",
                "schedule": crontab(minute=f"*/{max(1, tracker_reset_interval_minutes)}", hour="*"),
                "kwargs": {"stale_minutes": max(1, tracker_stale_minutes)},
            }

        app.conf.beat_schedule = beat_schedule

    return app


celery_app = make_celery_app()
