from __future__ import annotations

from pathlib import Path

from celery_app import celery_app
from worker import process_zip_job


@celery_app.task(name="celery_tasks.tasks.zip_tasks.process_zip_job_task", bind=True, acks_late=True)
def process_zip_job_task(
    self,
    job_token: str,
    saved_paths: list[str],
    user_id: int | None = None,
    hospital_id: int | None = None,
) -> None:
    paths = [Path(p) for p in saved_paths]
    process_zip_job(job_token, paths)
