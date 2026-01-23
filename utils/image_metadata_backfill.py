from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from auth.utils import utcnow
from db_transaction_manager import get_db_session
from models import (
    DirectImageUpload,
    EncounterFile,
    IMAGE_DIR,
    ImageMetadata,
    ImagePiiVerification,
    PatientEncounters,
    ZipFile,
)
from utils.fileUtils import abs_from_parts
from utils.image_metadata import extract_image_metadata, upsert_image_metadata
from utils.log_sanitize import sanitize_log_value
from utils.pii_verification import run_pii_detection_for_path

_LOGGER = logging.getLogger("image_metadata_backfill")


@dataclass(frozen=True)
class ImageWorkItem:
    image_uuid: str
    image_variant: str
    path: Path
    encounter_file_id: Optional[int] = None
    direct_image_upload_id: Optional[int] = None


def _needs_metadata(db, image_uuid: str, image_variant: str) -> bool:
    return not (
        db.query(ImageMetadata.id)
        .filter(
            ImageMetadata.image_uuid == image_uuid,
            ImageMetadata.image_variant == image_variant,
        )
        .first()
    )


def _needs_pii(db, image_uuid: str, image_variant: str) -> bool:
    return not (
        db.query(ImagePiiVerification.id)
        .filter(
            ImagePiiVerification.image_uuid == image_uuid,
            ImagePiiVerification.image_variant == image_variant,
        )
        .first()
    )


def _iter_encounter_items(db) -> Iterable[ImageWorkItem]:
    rows = (
        db.query(EncounterFile.id, EncounterFile.uuid, EncounterFile.filename, ZipFile.upload_date)
        .join(PatientEncounters, EncounterFile.patient_encounter_id == PatientEncounters.id)
        .join(ZipFile, PatientEncounters.zip_file_id == ZipFile.id)
        .order_by(EncounterFile.id.asc())
        .all()
    )
    for enc_id, image_uuid, filename, upload_date in rows:
        if not image_uuid or not filename or not upload_date:
            continue
        date_str = upload_date.strftime("%Y_%m_%d")
        path = (IMAGE_DIR / date_str / filename).resolve()
        yield ImageWorkItem(
            image_uuid=str(image_uuid),
            image_variant="orig",
            path=path,
            encounter_file_id=enc_id,
        )


def _iter_direct_items(db) -> Iterable[ImageWorkItem]:
    rows = (
        db.query(DirectImageUpload.id, DirectImageUpload.uuid, DirectImageUpload.folder_rel, DirectImageUpload.filename, DirectImageUpload.edited_filename)
        .order_by(DirectImageUpload.id.asc())
        .all()
    )
    for upload_id, image_uuid, folder_rel, filename, edited_filename in rows:
        if not image_uuid or not folder_rel or not filename:
            continue
        try:
            orig_path = abs_from_parts(folder_rel, filename, kind="orig")
        except Exception as exc:
            _LOGGER.warning(
                "Invalid direct upload path for %s: %s",
                sanitize_log_value(image_uuid),
                sanitize_log_value(exc),
            )
            continue
        yield ImageWorkItem(
            image_uuid=str(image_uuid),
            image_variant="orig",
            path=orig_path,
            direct_image_upload_id=upload_id,
        )
        if edited_filename:
            try:
                edited_path = abs_from_parts(folder_rel, edited_filename, kind="edited")
            except Exception as exc:
                _LOGGER.warning(
                    "Invalid edited path for %s: %s",
                    sanitize_log_value(image_uuid),
                    sanitize_log_value(exc),
                )
                continue
            yield ImageWorkItem(
                image_uuid=str(image_uuid),
                image_variant="edited",
                path=edited_path,
                direct_image_upload_id=upload_id,
            )


def run_image_metadata_backfill(limit: Optional[int] = None) -> int:
    try:
        os.nice(10)
    except Exception:
        pass

    processed = 0
    with get_db_session() as db:
        items = list(_iter_encounter_items(db)) + list(_iter_direct_items(db))

    for item in items:
        if limit is not None and processed >= limit:
            break
        with get_db_session() as db:
            if not item.path.exists():
                _LOGGER.warning(
                    "Image missing for %s (%s): %s",
                    sanitize_log_value(item.image_uuid),
                    sanitize_log_value(item.image_variant),
                    sanitize_log_value(str(item.path)),
                )
                continue

            metadata_needed = _needs_metadata(db, item.image_uuid, item.image_variant)
            pii_needed = _needs_pii(db, item.image_uuid, item.image_variant)
            if not metadata_needed and not pii_needed:
                continue

            if metadata_needed:
                meta_result = extract_image_metadata(image_path=item.path)
                upsert_image_metadata(
                    db,
                    image_uuid=item.image_uuid,
                    image_variant=item.image_variant,
                    encounter_file_id=item.encounter_file_id,
                    direct_image_upload_id=item.direct_image_upload_id,
                    metadata=meta_result,
                )

            if pii_needed:
                run_pii_detection_for_path(
                    db,
                    image_uuid=item.image_uuid,
                    image_variant=item.image_variant,
                    image_path=str(item.path),
                )

            db.commit()
            processed += 1

        time.sleep(1)

    _LOGGER.info("Image metadata backfill processed=%s", sanitize_log_value(processed))
    return processed


def enqueue_image_metadata_backfill(app, limit: Optional[int] = None) -> None:
    executor = app.config.get("EXECUTOR")
    if executor is None:
        return

    def _worker(app_ref, limit_val):
        with app_ref.app_context():
            run_image_metadata_backfill(limit=limit_val)

    executor.submit(_worker, app, limit)
