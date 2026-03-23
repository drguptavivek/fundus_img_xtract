from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytz

from admin import status as admin_status


def test_build_celery_task_status_payload_flags_duplicates_and_missing_queue():
    now = datetime(2026, 3, 23, 6, 0, tzinfo=pytz.UTC)
    db_row = SimpleNamespace(
        name="reset-stuck-task-trackers",
        task_name="celery_tasks.tasks.maintenance_tasks.reset_stuck_task_trackers_task",
        queue=None,
        enabled=True,
        schedule_type="interval",
        interval_seconds=1800,
        crontab_minute=None,
        crontab_hour=None,
        crontab_day_of_week=None,
        crontab_day_of_month=None,
        crontab_month_of_year=None,
        last_run_at=None,
        next_run_at=None,
    )
    code_entries = {
        "task-tracker-reset-stale-locks": {
            "task": "celery_tasks.tasks.maintenance_tasks.reset_stuck_task_trackers_task",
            "schedule": SimpleNamespace(run_every=SimpleNamespace(total_seconds=lambda: 1800)),
        }
    }

    payload = admin_status._build_celery_task_status_payload([db_row], code_entries, now)

    assert payload["summary"]["warning_count"] == 2
    db_entry = next(row for row in payload["rows"] if row["source"] == "db")
    assert db_entry["queue"] == "maintenance"
    assert "Duplicate schedule definition (2 total)" in db_entry["issues"]
    assert "No persisted run telemetry" in db_entry["issues"]


def test_build_celery_task_status_payload_marks_disabled_rows_and_preserves_explicit_queue():
    now = datetime(2026, 3, 23, 6, 0, tzinfo=pytz.UTC)
    db_row = SimpleNamespace(
        name="cleanup-stuck-jobs",
        task_name="celery_tasks.tasks.maintenance_tasks.cleanup_stuck_jobs_task",
        queue="maintenance",
        enabled=False,
        schedule_type="interval",
        interval_seconds=1800,
        crontab_minute=None,
        crontab_hour=None,
        crontab_day_of_week=None,
        crontab_day_of_month=None,
        crontab_month_of_year=None,
        last_run_at=None,
        next_run_at=None,
    )

    payload = admin_status._build_celery_task_status_payload([db_row], {}, now)

    assert payload["summary"]["disabled_count"] == 1
    db_entry = payload["rows"][0]
    assert db_entry["status"] == "disabled"
    assert db_entry["queue"] == "maintenance"
    assert db_entry["queue_explicit"] is True


def test_build_celery_task_status_payload_coerces_iso_datetime_strings():
    now = datetime(2026, 3, 23, 6, 0, tzinfo=pytz.UTC)
    db_row = {
        "name": "cleanup-stuck-jobs",
        "task_name": "celery_tasks.tasks.maintenance_tasks.cleanup_stuck_jobs_task",
        "queue": "maintenance",
        "enabled": True,
        "schedule_type": "interval",
        "interval_seconds": 1800,
        "crontab_minute": None,
        "crontab_hour": None,
        "crontab_day_of_week": None,
        "crontab_day_of_month": None,
        "crontab_month_of_year": None,
        "last_run_at": "2026-03-23T05:30:00+00:00",
        "next_run_at": "2026-03-23T06:00:00+00:00",
    }

    payload = admin_status._build_celery_task_status_payload([db_row], {}, now)

    entry = payload["rows"][0]
    assert entry["last_run_at"].isoformat() == "2026-03-23T05:30:00+00:00"
    assert entry["next_run_at"].isoformat() == "2026-03-23T06:00:00+00:00"
    assert entry["issues"] == []
