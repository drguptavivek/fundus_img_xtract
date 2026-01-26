from __future__ import annotations

import os
from typing import Any

from celery_app import celery_app


def celery_enabled() -> bool:
    return str(os.getenv("CELERY_ENABLED", "true")).lower() in ("1", "true", "yes")


def enqueue_task(task_name: str, *args: Any, user_id: int | None = None, hospital_id: int | None = None, **kwargs: Any):
    if "user_id" not in kwargs:
        kwargs["user_id"] = user_id
    if "hospital_id" not in kwargs:
        kwargs["hospital_id"] = hospital_id
    return celery_app.send_task(task_name, args=args, kwargs=kwargs)
