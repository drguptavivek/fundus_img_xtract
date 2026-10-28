from __future__ import annotations

from celery_app import celery_app
from remidio_api_integration.service import (
    create_daily_self_healing_project_sync_jobs,
    create_prospective_project_sync_jobs,
    create_weekly_audit_project_sync_jobs,
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
    _ = self, hospital_id
    return run_routing_profile_sync_job(job_id, expected_user_id=user_id)


@celery_app.task(name="celery_tasks.tasks.remidio_tasks.run_remidio_api_project_sync_task", bind=True, acks_late=True)
def run_remidio_api_project_sync_task(
    self,
    job_id: int,
    user_id: int | None = None,
    hospital_id: int | None = None,
) -> dict:
    _ = self, hospital_id
    return run_project_sync_job(job_id, expected_user_id=user_id)


@celery_app.task(name="celery_tasks.tasks.remidio_tasks.queue_remidio_api_prospective_project_syncs_task", bind=True, acks_late=True)
def queue_remidio_api_prospective_project_syncs_task(self) -> dict:
    _ = self
    return create_prospective_project_sync_jobs()


@celery_app.task(name="celery_tasks.tasks.remidio_tasks.queue_remidio_api_daily_self_heal_task", bind=True, acks_late=True)
def queue_remidio_api_daily_self_heal_task(self) -> dict:
    _ = self
    return create_daily_self_healing_project_sync_jobs()


@celery_app.task(name="celery_tasks.tasks.remidio_tasks.queue_remidio_api_weekly_audit_task", bind=True, acks_late=True)
def queue_remidio_api_weekly_audit_task(self) -> dict:
    _ = self
    return create_weekly_audit_project_sync_jobs()


@celery_app.task(name="celery_tasks.tasks.remidio_tasks.repull_remidio_images_task", bind=True, acks_late=True)
def repull_remidio_images_task(
    self,
    limit_images: int = 50,
    before: str | None = None,
    batches: int = 1,
    dry_run: bool = False,
    user_id: int | None = None,
    hospital_id: int | None = None,
) -> dict:
    """Restore full-fidelity Remidio images, newest exams first; see remidio_api_integration.image_repull.

    Chains itself (30 s apart) for ``batches`` batches so the provider is never hit in a burst.
    """
    from datetime import date

    from remidio_api_integration.image_repull import repull_batch

    _ = user_id, hospital_id

    summary = repull_batch(
        limit_images=limit_images,
        before=date.fromisoformat(before) if before else None,
        dry_run=dry_run,
    )
    result = summary.as_dict()
    if not dry_run and not summary.done and summary.next_before and batches > 1:
        self.apply_async(
            kwargs={"limit_images": limit_images, "before": summary.next_before, "batches": batches - 1},
            countdown=30,
        )
        result["next_batch_queued"] = True
    return result
