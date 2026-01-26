from __future__ import annotations

from celery_app import celery_app
from review.discrepancy_export import run_discrepancy_export_job, run_dataset_export_job


@celery_app.task(name="celery_tasks.tasks.export_tasks.run_discrepancy_export_task", bind=True, acks_late=True)
def run_discrepancy_export_task(
    self,
    job_token: str,
    filters: dict,
    user_context: dict,
    user_id: int | None = None,
    hospital_id: int | None = None,
) -> None:
    run_discrepancy_export_job(job_token, filters, user_context)


@celery_app.task(name="celery_tasks.tasks.export_tasks.run_dataset_export_task", bind=True, acks_late=True)
def run_dataset_export_task(
    self,
    job_token: str,
    dataset_id: int,
    task_ids: list[int],
    metadata: dict,
    user_id: int | None = None,
    hospital_id: int | None = None,
) -> None:
    run_dataset_export_job(job_token, dataset_id, task_ids, metadata)
