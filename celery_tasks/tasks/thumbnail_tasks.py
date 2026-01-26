from __future__ import annotations

from celery_app import celery_app
from utils.thumbnail_jobs import process_thumbnail_job


@celery_app.task(name="celery_tasks.tasks.thumbnail_tasks.process_thumbnail_job_task", bind=True, acks_late=True)
def process_thumbnail_job_task(self, job_token: str, user_id: int | None = None, hospital_id: int | None = None) -> None:
    process_thumbnail_job(job_token)
