from __future__ import annotations

import json
import logging
from typing import Any, Optional

from auth.utils import utcnow
from models import ImagePiiVerification
from utils.log_sanitize import sanitize_log_value

_LOGGER = logging.getLogger("pii_verification")


def _get_existing(db, image_uuid: str, image_variant: str) -> Optional[ImagePiiVerification]:
    return (
        db.query(ImagePiiVerification)
        .filter(
            ImagePiiVerification.image_uuid == image_uuid,
            ImagePiiVerification.image_variant == image_variant,
        )
        .first()
    )


def upsert_pii_verification(
    db,
    *,
    image_uuid: str,
    image_variant: str,
    ocr_result: dict[str, Any],
    source: str = "auto",
) -> Optional[ImagePiiVerification]:
    existing = _get_existing(db, image_uuid, image_variant)
    if existing and existing.source == "manual":
        return None
    if existing:
        return existing

    status = "detected" if ocr_result.get("is_pii") else "clear"
    detections = ocr_result.get("detections", [])
    roi = ocr_result.get("roi")
    record = ImagePiiVerification(
        image_uuid=image_uuid,
        image_variant=image_variant,
        pii_status=status,
        source=source,
        detections_json=json.dumps(detections, ensure_ascii=True, separators=(",", ":")),
        roi_json=json.dumps(roi, ensure_ascii=True, separators=(",", ":")) if roi else None,
        checked_at=utcnow(),
    )
    db.add(record)
    return record


def run_pii_detection_for_path(
    db,
    *,
    image_uuid: str,
    image_variant: str,
    image_path: str,
) -> Optional[ImagePiiVerification]:
    from utils.ocr_pii import detect_pii_details_for_path

    existing = _get_existing(db, image_uuid, image_variant)
    if existing and existing.source == "manual":
        return None
    if existing:
        return existing

    try:
        ocr_result = detect_pii_details_for_path(image_path)
    except Exception as exc:
        _LOGGER.warning(
            "PII detection failed for %s (%s): %s",
            sanitize_log_value(image_uuid),
            sanitize_log_value(image_variant),
            sanitize_log_value(exc),
        )
        return None

    return upsert_pii_verification(
        db,
        image_uuid=image_uuid,
        image_variant=image_variant,
        ocr_result=ocr_result,
        source="auto",
    )


def enqueue_pii_detection(app, image_uuid: str, image_variant: str, image_path: str) -> None:
    from utils.pii_detection_queue import enqueue_pii_detection as enqueue_pii_detection_queue

    enqueue_pii_detection_queue(app, image_uuid, image_variant, image_path)
