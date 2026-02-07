from __future__ import annotations

import logging

from celery_app import celery_app
from utils.celery_context import build_task_app
from utils.log_sanitize import sanitize_log_value
from utils.mvw_image_listing_v2 import ensure_per_disease_image_listing_mvs

_LOGGER = logging.getLogger("materialized_view_v2")


@celery_app.task(
    name="celery_tasks.tasks.mv_tasks.refresh_image_listing_v2_task",
    bind=True,
    acks_late=True,
)
def refresh_image_listing_v2_task(self, schedule_time: str | None = None) -> dict:
    _ = build_task_app()
    results = ensure_per_disease_image_listing_mvs(
        schedule_time=schedule_time or "celery_beat",
        create_missing=False,
        refresh_existing=True,
    )
    _LOGGER.info("mvw_image_listing_v2 refresh results: %s", sanitize_log_value(results))
    return results


@celery_app.task(
    name="celery_tasks.tasks.mv_tasks.ensure_image_listing_v2_task",
    bind=True,
    acks_late=True,
)
def ensure_image_listing_v2_task(self, schedule_time: str | None = None) -> dict:
    _ = build_task_app()
    results = ensure_per_disease_image_listing_mvs(
        schedule_time=schedule_time or "celery_beat",
        create_missing=True,
        refresh_existing=False,
    )
    _LOGGER.info("mvw_image_listing_v2 ensure results: %s", sanitize_log_value(results))
    return results
