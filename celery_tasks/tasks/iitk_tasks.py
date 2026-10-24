"""Celery entrypoints for IITK API synchronization."""
from __future__ import annotations

from celery_app import celery_app
from iitk_api_integration.service import (
    queue_active_config_syncs,
    recover_stale_config_syncs,
    resync_incomplete_sessions,
    sync_config,
)


@celery_app.task(
    name="celery_tasks.tasks.iitk_tasks.run_iitk_config_sync_task",
    bind=True,
    acks_late=True,
)
def run_iitk_config_sync_task(self, config_id: int, full: bool = False) -> dict:
    _ = self
    return sync_config(config_id, full=full)


@celery_app.task(
    name="celery_tasks.tasks.iitk_tasks.queue_active_iitk_syncs_task",
    bind=True,
    acks_late=True,
    max_retries=1,
)
def queue_active_iitk_syncs_task(self) -> dict:
    try:
        return queue_active_config_syncs()
    except Exception as exc:
        raise self.retry(exc=exc, countdown=5) from exc


@celery_app.task(
    name="celery_tasks.tasks.iitk_tasks.recover_stale_iitk_syncs_task",
    bind=True,
    acks_late=True,
)
def recover_stale_iitk_syncs_task(self) -> dict:
    _ = self
    return recover_stale_config_syncs()


@celery_app.task(
    name="celery_tasks.tasks.iitk_tasks.resync_incomplete_iitk_sessions_task",
    bind=True,
    acks_late=True,
)
def resync_incomplete_iitk_sessions_task(self, config_id: int) -> dict:
    """Re-fetch sessions whose images were uploaded after the session closed."""
    _ = self
    return resync_incomplete_sessions(config_id)


@celery_app.task(name="celery_tasks.tasks.iitk_tasks.repull_iitk_images_task", bind=True, acks_late=True)
def repull_iitk_images_task(
    self,
    limit_images: int = 50,
    before: str | None = None,
    batches: int = 1,
    dry_run: bool = False,
    user_id: int | None = None,
) -> dict:
    """Restore full-fidelity IITK images, newest first; see iitk_api_integration.image_repull.

    Chains itself (30 s apart) for ``batches`` batches so the provider is never hit in a burst.
    """
    from datetime import date

    from iitk_api_integration.image_repull import repull_batch

    _ = user_id
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
