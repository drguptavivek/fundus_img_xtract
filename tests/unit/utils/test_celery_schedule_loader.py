from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from types import SimpleNamespace

import pytz

from utils import celery_schedule_loader


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def all(self):
        return self._rows


class _FakeDb:
    def __init__(self, rows):
        self._rows = rows

    def query(self, _model):
        return _FakeQuery(self._rows)


def _row(**overrides):
    values = {
        "name": "reset-stuck-task-trackers",
        "task_name": "celery_tasks.tasks.maintenance_tasks.reset_stuck_task_trackers_task",
        "schedule_type": "interval",
        "interval_seconds": 1800,
        "crontab_minute": None,
        "crontab_hour": None,
        "crontab_day_of_week": None,
        "crontab_day_of_month": None,
        "crontab_month_of_year": None,
        "queue": None,
        "user_id": None,
        "hospital_id": None,
        "last_run_at": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _patch_transaction_scope(monkeypatch, rows):
    @contextmanager
    def fake_transaction_scope():
        yield _FakeDb(rows)

    monkeypatch.setattr(celery_schedule_loader, "transaction_scope", fake_transaction_scope)


def test_load_db_celery_schedules_infers_queue_for_known_task(monkeypatch):
    _patch_transaction_scope(monkeypatch, [_row()])

    schedules = celery_schedule_loader.load_db_celery_schedules()

    entry = schedules["reset-stuck-task-trackers"]
    assert entry["task"] == "celery_tasks.tasks.maintenance_tasks.reset_stuck_task_trackers_task"
    assert entry["options"] == {"queue": "maintenance"}
    assert "kwargs" not in entry


def test_load_db_celery_schedules_preserves_explicit_queue_and_filters_kwargs(monkeypatch):
    _patch_transaction_scope(
        monkeypatch,
        [
            _row(
                name="explicit-queue-task",
                queue="exports",
                task_name="celery_tasks.tasks.export_tasks.generate_export_task",
                user_id=12,
                hospital_id=None,
            )
        ],
    )

    schedules = celery_schedule_loader.load_db_celery_schedules()

    entry = schedules["explicit-queue-task"]
    assert entry["options"] == {"queue": "exports"}
    assert entry["kwargs"] == {"user_id": 12}


def test_load_db_celery_schedules_infers_queue_for_package_update_and_keeps_last_run(monkeypatch):
    last_run_at = datetime(2026, 3, 23, 6, 0, tzinfo=pytz.UTC)
    _patch_transaction_scope(
        monkeypatch,
        [
            _row(
                name="package-update-scan",
                task_name="celery_tasks.tasks.package_update_tasks.run_package_update_scan_task",
                schedule_type="crontab",
                interval_seconds=None,
                crontab_minute="0",
                crontab_hour="3",
                last_run_at=last_run_at,
            )
        ],
    )

    schedules = celery_schedule_loader.load_db_celery_schedules()

    entry = schedules["package-update-scan"]
    assert entry["options"] == {"queue": "maintenance"}
    assert entry["last_run_at"] == last_run_at


def test_load_db_celery_schedules_skips_interval_rows_without_interval(monkeypatch):
    _patch_transaction_scope(monkeypatch, [_row(name="broken-interval", interval_seconds=None)])

    schedules = celery_schedule_loader.load_db_celery_schedules()

    assert "broken-interval" not in schedules
