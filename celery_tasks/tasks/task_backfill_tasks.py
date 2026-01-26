from __future__ import annotations

from celery_app import celery_app
from utils.task_backfill import run_task_backfill_job


@celery_app.task(name="celery_tasks.tasks.task_backfill_tasks.run_task_backfill_job_task", bind=True, acks_late=True)
def run_task_backfill_job_task(self, job_id: int, user_id: int | None = None, hospital_id: int | None = None) -> None:
    run_task_backfill_job(job_id)
