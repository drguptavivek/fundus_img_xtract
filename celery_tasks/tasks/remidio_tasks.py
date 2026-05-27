from __future__ import annotations

from celery_app import celery_app
from remidio_api_integration.service import (
    create_prospective_project_sync_jobs,
    run_project_sync_job,
    run_routing_profile_sync_job,
)


@celery_app.task(name="celery_tasks.tasks.remidio_tasks.run_remidio_api_routing_profile_sync_task", bind=True, acks_late=True)
def run_remidio_api_routing_profile_sync_task(
    self,
    job_id: int,
    user_id: int | None = None,
    hospital_id: int | None = None,
) -> dict:
    _ = user_id, hospital_id
    return run_routing_profile_sync_job(job_id)


@celery_app.task(name="celery_tasks.tasks.remidio_tasks.run_remidio_api_project_sync_task", bind=True, acks_late=True)
def run_remidio_api_project_sync_task(
    self,
    job_id: int,
    user_id: int | None = None,
    hospital_id: int | None = None,
) -> dict:
    _ = self, user_id, hospital_id
    return run_project_sync_job(job_id)


@celery_app.task(name="celery_tasks.tasks.remidio_tasks.queue_remidio_api_prospective_project_syncs_task", bind=True, acks_late=True)
def queue_remidio_api_prospective_project_syncs_task(self) -> dict:
    _ = self
    return create_prospective_project_sync_jobs()
