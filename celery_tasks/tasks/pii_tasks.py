from __future__ import annotations

from celery_app import celery_app
from utils.pii_detection_queue import run_pii_detection_queue


@celery_app.task(name="celery_tasks.tasks.pii_tasks.run_pii_detection_queue_task", bind=True, acks_late=True)
def run_pii_detection_queue_task(self, max_jobs: int | None = None, user_id: int | None = None, hospital_id: int | None = None) -> int:
    return run_pii_detection_queue(max_jobs=max_jobs)
