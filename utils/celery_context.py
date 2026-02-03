"""
Minimal app-like context for Celery tasks that need config.

Avoids importing Flask or app.py.
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from contextlib import contextmanager

from utils.env_loader import load_environment


@contextmanager
def _noop_context():
    yield


def build_task_app():
    load_environment()

    config = {
        "DEFAULT_DISPLAY_TIMEZONE": os.getenv("DEFAULT_DISPLAY_TIMEZONE", "Asia/Kolkata"),
        "MATERIALIZED_VIEW_TIMEZONE": os.getenv("MATERIALIZED_VIEW_TIMEZONE", os.getenv("DEFAULT_DISPLAY_TIMEZONE", "Asia/Kolkata")),
        "MATERIALIZED_VIEW_SCHEDULE_TIMES": os.getenv(
            "MATERIALIZED_VIEW_SCHEDULE_TIMES",
            ",".join([f"{h:02d}:{m:02d}" for h in range(24) for m in (0, 30)]),
        ).split(","),
        "MATERIALIZED_VIEW_RETRY_ATTEMPTS": int(os.getenv("MATERIALIZED_VIEW_RETRY_ATTEMPTS", "3")),
        "MATERIALIZED_VIEW_RETRY_DELAY_SECONDS": int(os.getenv("MATERIALIZED_VIEW_RETRY_DELAY_SECONDS", "60")),
        "THUMBNAIL_MAINTENANCE_TIMEZONE": os.getenv("THUMBNAIL_MAINTENANCE_TIMEZONE", os.getenv("DEFAULT_DISPLAY_TIMEZONE", "Asia/Kolkata")),
        "THUMBNAIL_MAINTENANCE_SCHEDULE_TIMES": os.getenv(
            "THUMBNAIL_MAINTENANCE_SCHEDULE_TIMES",
            "00:00,08:00,16:00",
        ).split(","),
        "THUMBNAIL_MAINTENANCE_CLEANUP_LIMIT": int(os.getenv("THUMBNAIL_MAINTENANCE_CLEANUP_LIMIT", "1000")),
        "THUMBNAIL_MAINTENANCE_REGENERATION_LIMIT": int(os.getenv("THUMBNAIL_MAINTENANCE_REGENERATION_LIMIT", "100")),
        "THUMBNAIL_MAINTENANCE_VALIDATION_SAMPLE_SIZE": int(os.getenv("THUMBNAIL_MAINTENANCE_VALIDATION_SAMPLE_SIZE", "200")),
    }

    app = SimpleNamespace(config=config)
    app.app_context = _noop_context
    return app
