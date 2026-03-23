from __future__ import annotations

import os
import time
from datetime import timedelta
from typing import Dict

from celery.beat import Scheduler

from db_transaction_manager import transaction_scope
from models import CeleryBeatSchedule
from utils.celery_schedule_loader import load_db_celery_schedules


def _env_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


class DatabaseScheduleScheduler(Scheduler):
    """Celery beat scheduler that refreshes schedules from the database."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._refresh_seconds = _env_int("CELERY_BEAT_DB_REFRESH_SECONDS", 60)
        self._last_refresh_ts = 0.0
        self._db_schedule_names: set[str] = set()

    def setup_schedule(self):
        self._load_schedule()

    def tick(self):
        if time.time() - self._last_refresh_ts >= self._refresh_seconds:
            self._load_schedule()
        return super().tick()

    def _load_schedule(self) -> None:
        raw_schedule: Dict = {}
        configured = self.app.conf.beat_schedule or {}
        if isinstance(configured, dict):
            raw_schedule.update(configured)

        db_schedule = load_db_celery_schedules()
        self._db_schedule_names = set(db_schedule.keys())
        raw_schedule.update(db_schedule)

        schedule_entries: Dict = {}
        for name, entry in raw_schedule.items():
            if hasattr(entry, "is_due"):
                schedule_entries[name] = entry
                continue
            if not isinstance(entry, dict):
                continue
            try:
                schedule_entries[name] = self.Entry(name=name, app=self.app, **entry)
            except Exception:
                continue

        self.schedule = schedule_entries
        self._last_refresh_ts = time.time()

    def reserve(self, entry):
        new_entry = super().reserve(entry)
        if entry.name in self._db_schedule_names:
            self._persist_entry_run_state(new_entry)
        return new_entry

    def _persist_entry_run_state(self, entry) -> None:
        next_run_at = None
        try:
            _, next_seconds = entry.is_due()
            next_run_at = entry.last_run_at + timedelta(seconds=float(next_seconds))
        except Exception:
            next_run_at = None

        with transaction_scope() as db:
            db.query(CeleryBeatSchedule).filter(CeleryBeatSchedule.name == entry.name).update(
                {
                    CeleryBeatSchedule.last_run_at: entry.last_run_at,
                    CeleryBeatSchedule.next_run_at: next_run_at,
                },
                synchronize_session=False,
            )
