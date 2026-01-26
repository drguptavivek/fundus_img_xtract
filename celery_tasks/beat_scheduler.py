from __future__ import annotations

import os
import time
from typing import Dict

from celery.beat import Scheduler

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
