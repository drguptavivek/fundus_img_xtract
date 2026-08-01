"""Celery entrypoints for IITK API synchronization."""
from __future__ import annotations

from celery_app import celery_app
from iitk_api_integration.service import queue_active_config_syncs, recover_stale_config_syncs, sync_config


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
