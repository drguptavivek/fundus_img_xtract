from __future__ import annotations

import logging
from uuid import uuid4

import redis
from celery.exceptions import MaxRetriesExceededError, Retry

from celery_app import celery_app
from utils.celery_context import build_task_app
from utils.log_sanitize import sanitize_log_value
from utils.mvw_image_listing_v2 import (
    ensure_per_disease_image_listing_mvs,
    refresh_image_listing_mv_for_disease,
)
from utils.redis_connection import build_redis_url

_LOGGER = logging.getLogger("materialized_view_v2")
_LOCK_TTL_SECONDS = 600
_DEBOUNCE_SECONDS = 30


def _redis_client():
    return redis.Redis.from_url(build_redis_url(), decode_responses=True)


def _keys(disease_id: int) -> tuple[str, str]:
    return (
        f"review-mv-refresh:dirty:{disease_id}",
        f"review-mv-refresh:scheduled:{disease_id}",
    )


def queue_debounced_image_listing_refresh(disease_id: int) -> bool:
    """Mark a disease dirty and ensure at most one trailing refresh is scheduled."""
    client = _redis_client()
    dirty_key, lock_key = _keys(disease_id)
    generation = str(uuid4())
    client.set(dirty_key, generation, ex=_LOCK_TTL_SECONDS)
    if not client.set(lock_key, generation, nx=True, ex=_LOCK_TTL_SECONDS):
        return False
    try:
        refresh_image_listing_v2_task.apply_async(
            kwargs={
                "disease_id": disease_id,
                "schedule_time": "review_submission",
                "scheduled_generation": generation,
            },
            countdown=_DEBOUNCE_SECONDS,
        )
    except Exception:
        client.delete(lock_key)
        raise
    return True


@celery_app.task(
    name="celery_tasks.tasks.mv_tasks.refresh_image_listing_v2_task",
    bind=True,
    acks_late=True,
    max_retries=3,
)
def refresh_image_listing_v2_task(
    self,
    schedule_time: str | None = None,
    disease_id: int | None = None,
    scheduled_generation: str | None = None,
) -> dict:
    _ = build_task_app()
    label = schedule_time or "celery_beat"
    if disease_id is None:
        results = ensure_per_disease_image_listing_mvs(
            schedule_time=label,
            create_missing=False,
            refresh_existing=True,
        )
        if results.get("errors"):
            raise self.retry(exc=RuntimeError(f"MV refresh errors: {results}"), countdown=30)
        _LOGGER.info("mvw_image_listing_v2 refresh results: %s", sanitize_log_value(results))
        return results

    client = _redis_client()
    dirty_key, lock_key = _keys(disease_id)
    if scheduled_generation is not None and client.get(lock_key) != scheduled_generation:
        _LOGGER.info(
            "Skipping stale disease MV refresh disease_id=%s",
            sanitize_log_value(disease_id),
        )
        return {
            "disease_id": disease_id,
            "schedule_time": label,
            "refreshed": 0,
            "skipped": 1,
            "errors": 0,
        }
    generation_before = client.get(dirty_key)
    try:
        results = refresh_image_listing_mv_for_disease(disease_id, schedule_time=label)
        generation_after = client.get(dirty_key)
        if generation_after != generation_before:
            raise self.retry(countdown=_DEBOUNCE_SECONDS)
        pipeline = client.pipeline()
        pipeline.watch(dirty_key)
        if pipeline.get(dirty_key) == generation_before:
            pipeline.multi()
            pipeline.delete(dirty_key, lock_key)
            pipeline.execute()
        else:
            pipeline.reset()
            raise self.retry(countdown=_DEBOUNCE_SECONDS)
        _LOGGER.info("Disease MV refresh results: %s", sanitize_log_value(results))
        return results
    except MaxRetriesExceededError:
        client.delete(lock_key)
        raise
    except Retry:
        raise
    except Exception as exc:
        _LOGGER.exception("Disease MV refresh failed for disease_id=%s", disease_id)
        countdown = _DEBOUNCE_SECONDS if isinstance(exc, redis.WatchError) else 30
        try:
            raise self.retry(exc=exc, countdown=countdown)
        except MaxRetriesExceededError:
            client.delete(lock_key)
            raise


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
