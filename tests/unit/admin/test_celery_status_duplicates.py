from datetime import datetime, timezone

from admin.status import _build_celery_task_status_payload


def _thumbnail_row(name: str, minute: str, hour: str) -> dict:
    return {
        "name": name,
        "task_name": "celery_tasks.tasks.maintenance_tasks.regenerate_missing_thumbnails_task",
        "queue": "maintenance",
        "enabled": True,
        "schedule_type": "crontab",
        "interval_seconds": None,
        "crontab_minute": minute,
        "crontab_hour": hour,
        "crontab_day_of_week": "*",
        "crontab_day_of_month": "*",
        "crontab_month_of_year": "*",
        "last_run_at": datetime(2026, 5, 4, 8, 0, tzinfo=timezone.utc),
        "next_run_at": datetime(2026, 5, 5, 8, 0, tzinfo=timezone.utc),
    }


def test_same_task_with_different_cron_times_is_not_duplicate_warning():
    payload = _build_celery_task_status_payload(
        [
            _thumbnail_row("Thumbnail Regeneration (13:30 IST)", "0", "8"),
            _thumbnail_row("Thumbnail Regeneration (20:00 IST)", "30", "14"),
        ],
        {},
        datetime(2026, 5, 4, 10, 0, tzinfo=timezone.utc),
    )

    assert payload["summary"]["warning_count"] == 0
    assert [row["status"] for row in payload["rows"]] == ["healthy", "healthy"]


def test_same_task_same_queue_and_schedule_is_duplicate_warning():
    payload = _build_celery_task_status_payload(
        [
            _thumbnail_row("Thumbnail Regeneration A", "0", "8"),
            _thumbnail_row("Thumbnail Regeneration B", "0", "8"),
        ],
        {},
        datetime(2026, 5, 4, 10, 0, tzinfo=timezone.utc),
    )

    assert payload["summary"]["warning_count"] == 2
    assert all("Duplicate schedule definition (2 total)" in row["issues"] for row in payload["rows"])
