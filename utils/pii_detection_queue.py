from __future__ import annotations

import logging
import time
from typing import Optional

from sqlalchemy import text

from auth.utils import utcnow
from db_transaction_manager import get_db_session
from models import ImagePiiVerification, PiiDetectionJob
from utils.log_sanitize import sanitize_log_value
from utils.pii_verification import run_pii_detection_for_path

_LOGGER = logging.getLogger("pii_detection_queue")
_PII_LOGGER = logging.getLogger("pii_detection")
_LOCK_KEY = 912348761


def enqueue_pii_detection_job(
    db,
    *,
    image_uuid: str,
    image_variant: str,
    image_path: str,
    source: str = "auto",
) -> Optional[int]:
    if not image_uuid or not image_variant or not image_path:
        return None

    existing_verification = (
        db.query(ImagePiiVerification.id)
        .filter(
            ImagePiiVerification.image_uuid == image_uuid,
            ImagePiiVerification.image_variant == image_variant,
            ImagePiiVerification.source == "manual",
        )
        .first()
    )
    if existing_verification:
        return None

    existing_job = (
        db.query(PiiDetectionJob)
        .filter(
            PiiDetectionJob.image_uuid == image_uuid,
            PiiDetectionJob.image_variant == image_variant,
            PiiDetectionJob.status.in_(["queued", "running"]),
        )
        .first()
    )
    if existing_job:
        return existing_job.id

    job = PiiDetectionJob(
        image_uuid=image_uuid,
        image_variant=image_variant,
        image_path=image_path,
        status="queued",
        attempts=0,
        source=source,
        created_at=utcnow(),
    )
    db.add(job)
    db.flush()
    _PII_LOGGER.info(
        "PII job queued for %s (%s)",
        sanitize_log_value(image_uuid),
        sanitize_log_value(image_variant),
    )
    return job.id


def _try_acquire_lock(db) -> bool:
    result = db.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": _LOCK_KEY}).scalar()
    return bool(result)


def _release_lock(db) -> None:
    db.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": _LOCK_KEY})


def run_pii_detection_queue(max_jobs: Optional[int] = None) -> int:
    processed = 0
    with get_db_session() as db:
        if not _try_acquire_lock(db):
            return 0
        try:
            while True:
                if max_jobs is not None and processed >= max_jobs:
                    break
                job = (
                    db.query(PiiDetectionJob)
                    .filter(PiiDetectionJob.status == "queued")
                    .order_by(PiiDetectionJob.created_at.asc())
                    .with_for_update(skip_locked=True)
                    .first()
                )
                if not job:
                    break

                job.status = "running"
                job.started_at = utcnow()
                job.attempts = (job.attempts or 0) + 1
                db.add(job)
                db.commit()

                try:
                    result = run_pii_detection_for_path(
                        db,
                        image_uuid=job.image_uuid,
                        image_variant=job.image_variant,
                        image_path=job.image_path,
                    )
                    job.status = "completed"
                    job.finished_at = utcnow()
                    if result is None:
                        job.error_message = "Skipped (manual override or existing)"
                        _PII_LOGGER.info(
                            "PII job skipped for %s (%s)",
                            sanitize_log_value(job.image_uuid),
                            sanitize_log_value(job.image_variant),
                        )
                    else:
                        _PII_LOGGER.info(
                            "PII job completed for %s (%s)",
                            sanitize_log_value(job.image_uuid),
                            sanitize_log_value(job.image_variant),
                        )
                except Exception as exc:  # noqa: BLE001
                    job.status = "failed"
                    job.error_message = str(exc)
                    job.finished_at = utcnow()
                    _LOGGER.warning(
                        "PII detection failed for %s (%s): %s",
                        sanitize_log_value(job.image_uuid),
                        sanitize_log_value(job.image_variant),
                        sanitize_log_value(exc),
                    )
                    _PII_LOGGER.warning(
                        "PII job failed for %s (%s): %s",
                        sanitize_log_value(job.image_uuid),
                        sanitize_log_value(job.image_variant),
                        sanitize_log_value(exc),
                    )

                db.add(job)
                db.commit()
                processed += 1
                time.sleep(3)
        finally:
            _release_lock(db)
    return processed


def enqueue_pii_detection(app, image_uuid: str, image_variant: str, image_path: str) -> None:
    def _worker(app_ref, uuid_val, variant_val, path_val):
        with app_ref.app_context():
            with get_db_session() as db:
                enqueue_pii_detection_job(
                    db,
                    image_uuid=uuid_val,
                    image_variant=variant_val,
                    image_path=path_val,
                    source="auto",
                )
            run_pii_detection_queue()

    try:
        executor = app.config.get("EXECUTOR")
        if executor is None:
            return
        executor.submit(_worker, app, image_uuid, image_variant, image_path)
    except Exception as exc:
        _LOGGER.warning(
            "Failed to enqueue PII detection for %s (%s): %s",
            sanitize_log_value(image_uuid),
            sanitize_log_value(image_variant),
            sanitize_log_value(exc),
        )
