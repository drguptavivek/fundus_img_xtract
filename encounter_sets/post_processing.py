"""Shared post-processing queueing for newly stored EncounterSet images.

Ingestion paths write image bytes to disk, but metadata extraction and
burned-in-PII detection run afterwards through Celery. Every path that stores
clinical images must queue this, or those images silently never get scanned.
"""
from __future__ import annotations

import logging

from utils.log_sanitize import sanitize_log_value

logger = logging.getLogger("encounter_sets.post_processing")


def queue_image_post_processing(image_ids, *, user_id: int | None = None, run_pii: bool = True) -> int:
    """Queue thumbnail + metadata/PII processing for stored EncounterSet images.

    Returns the number of images queued. Never raises: post-processing is
    valuable but must not fail an ingestion that has already written its rows.

    Falls back to running inline when Celery is disabled, matching the behaviour
    the rest of the ingestion pipeline relies on in tests and single-process
    deployments.

    ``run_pii=False`` skips the burned-in-PII scan for sources whose images are
    trusted not to carry it (Remidio camera exports); metadata extraction and the
    lossless EXIF strip still run.
    """
    ids = [int(image_id) for image_id in dict.fromkeys(image_ids or []) if image_id]
    if not ids:
        return 0

    try:
        from celery import chain

        from celery_tasks.tasks.encounter_set_tasks import (
            process_encounter_set_image_data_combined_task,
            process_encounter_set_image_thumbnail_task,
        )
        from utils.celery_helpers import celery_enabled

        queued = 0
        if celery_enabled():
            for image_id in ids:
                chain(
                    process_encounter_set_image_thumbnail_task.s(image_id, user_id=user_id),
                    process_encounter_set_image_data_combined_task.s(run_pii=run_pii),
                ).apply_async()
                queued += 1
        else:
            for image_id in ids:
                visual_result = process_encounter_set_image_thumbnail_task.run(image_id, user_id=user_id)
                process_encounter_set_image_data_combined_task.run(visual_result, run_pii=run_pii)
                queued += 1
        logger.info("Queued EncounterSet image post-processing count=%s", sanitize_log_value(queued))
        return queued
    except Exception as exc:  # noqa: BLE001 - ingestion has already committed
        logger.error(
            "Could not queue EncounterSet image post-processing: %s",
            sanitize_log_value(exc),
            exc_info=True,
        )
        return 0
