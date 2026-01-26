from __future__ import annotations

from celery_app import celery_app
from utils.image_metadata_backfill import run_image_metadata_backfill_job


@celery_app.task(name="celery_tasks.tasks.metadata_tasks.run_image_metadata_backfill_job_task", bind=True, acks_late=True)
def run_image_metadata_backfill_job_task(self, job_id: int, user_id: int | None = None, hospital_id: int | None = None) -> None:
    run_image_metadata_backfill_job(job_id)
