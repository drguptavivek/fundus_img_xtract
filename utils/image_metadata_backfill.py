from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import json
from auth.utils import utcnow
from sqlalchemy import func
from db_transaction_manager import get_db_session
from models import (
    DirectImageUpload,
    EncounterFile,
    IMAGE_DIR,
    ImageMetadataBackfillJob,
    ImageMetadata,
    ImagePiiVerification,
    PatientEncounters,
    ZipFile,
)
from utils.fileUtils import abs_from_parts
from utils.image_metadata import extract_image_metadata, upsert_image_metadata
from utils.log_sanitize import sanitize_log_value
from utils.pii_detection_queue import enqueue_pii_detection_job, run_pii_detection_queue

_LOGGER = logging.getLogger("image_metadata_backfill")
_METADATA_LOGGER = logging.getLogger("image_metadata")
_PII_SLEEP_SECONDS = 3
_ITEM_SLEEP_SECONDS = 3


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


def _apply_lab_unit_scope(query, allowed_lab_unit_ids: set[int]):
    if not allowed_lab_unit_ids:
        return query.filter(False)
    return query.filter(
        (EncounterFile.lab_unit_id.in_(allowed_lab_unit_ids))
        | (PatientEncounters.lab_unit_id.in_(allowed_lab_unit_ids))
    )


def _iter_encounter_items(db, *, allowed_lab_unit_ids: set[int]) -> Iterable[ImageWorkItem]:
    query = (
        db.query(EncounterFile.id, EncounterFile.uuid, EncounterFile.filename, ZipFile.upload_date)
        .join(PatientEncounters, EncounterFile.patient_encounter_id == PatientEncounters.id)
        .join(ZipFile, PatientEncounters.zip_file_id == ZipFile.id)
    )
    query = _apply_lab_unit_scope(query, allowed_lab_unit_ids)
    rows = query.order_by(EncounterFile.id.asc()).all()
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


def _iter_direct_items(db, *, allowed_lab_unit_ids: set[int]) -> Iterable[ImageWorkItem]:
    if not allowed_lab_unit_ids:
        return []
    rows = (
        db.query(DirectImageUpload.id, DirectImageUpload.uuid, DirectImageUpload.folder_rel, DirectImageUpload.filename, DirectImageUpload.edited_filename)
        .filter(DirectImageUpload.lab_unit_id.in_(allowed_lab_unit_ids))
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


def _count_missing_candidates(
    db,
    *,
    allowed_lab_unit_ids: set[int],
    run_metadata: bool,
    run_pii: bool,
) -> int:
    if not allowed_lab_unit_ids:
        return 0
    if not run_metadata and not run_pii:
        return 0

    if run_metadata and run_pii:
        missing_clause = (ImageMetadata.id.is_(None)) | (ImagePiiVerification.id.is_(None))
    elif run_metadata:
        missing_clause = ImageMetadata.id.is_(None)
    else:
        missing_clause = ImagePiiVerification.id.is_(None)
    encounter_query = (
        db.query(EncounterFile.id)
        .join(PatientEncounters, EncounterFile.patient_encounter_id == PatientEncounters.id)
        .join(ZipFile, PatientEncounters.zip_file_id == ZipFile.id)
        .outerjoin(
            ImageMetadata,
            (ImageMetadata.image_uuid == EncounterFile.uuid)
            & (ImageMetadata.image_variant == "orig"),
        )
        .outerjoin(
            ImagePiiVerification,
            (ImagePiiVerification.image_uuid == EncounterFile.uuid)
            & (ImagePiiVerification.image_variant == "orig"),
        )
    )
    encounter_query = _apply_lab_unit_scope(encounter_query, allowed_lab_unit_ids)
    encounter_missing = encounter_query.filter(missing_clause).count()

    direct_base = (
        db.query(DirectImageUpload.id, DirectImageUpload.uuid, DirectImageUpload.edited_filename)
        .filter(DirectImageUpload.lab_unit_id.in_(allowed_lab_unit_ids))
    )

    direct_missing = (
        direct_base.outerjoin(
            ImageMetadata,
            (ImageMetadata.image_uuid == DirectImageUpload.uuid)
            & (ImageMetadata.image_variant == "orig"),
        )
        .outerjoin(
            ImagePiiVerification,
            (ImagePiiVerification.image_uuid == DirectImageUpload.uuid)
            & (ImagePiiVerification.image_variant == "orig"),
        )
        .filter(missing_clause)
        .count()
    )

    edited_missing = (
        direct_base.filter(DirectImageUpload.edited_filename.isnot(None))
        .outerjoin(
            ImageMetadata,
            (ImageMetadata.image_uuid == DirectImageUpload.uuid)
            & (ImageMetadata.image_variant == "edited"),
        )
        .outerjoin(
            ImagePiiVerification,
            (ImagePiiVerification.image_uuid == DirectImageUpload.uuid)
            & (ImagePiiVerification.image_variant == "edited"),
        )
        .filter(missing_clause)
        .count()
    )

    return int(encounter_missing + direct_missing + edited_missing)


def get_missing_metadata_counts(db, *, allowed_lab_unit_ids: set[int]) -> dict[str, int]:
    if not allowed_lab_unit_ids:
        return {"encounter": 0, "direct": 0, "direct_edited": 0}

    total = get_total_image_counts(db, allowed_lab_unit_ids=allowed_lab_unit_ids)
    present = get_present_metadata_counts(db, allowed_lab_unit_ids=allowed_lab_unit_ids)
    return {
        "encounter": max(0, total["encounter"] - present["encounter"]),
        "direct": max(0, total["direct"] - present["direct"]),
        "direct_edited": max(0, total["direct_edited"] - present["direct_edited"]),
    }


def get_total_image_counts(db, *, allowed_lab_unit_ids: set[int]) -> dict[str, int]:
    if not allowed_lab_unit_ids:
        return {"encounter": 0, "direct": 0, "direct_edited": 0}

    encounter_query = (
        db.query(EncounterFile.id)
        .join(PatientEncounters, EncounterFile.patient_encounter_id == PatientEncounters.id)
        .join(ZipFile, PatientEncounters.zip_file_id == ZipFile.id)
    )
    encounter_query = _apply_lab_unit_scope(encounter_query, allowed_lab_unit_ids)
    encounter_total = encounter_query.count()

    direct_total = (
        db.query(DirectImageUpload.id)
        .filter(DirectImageUpload.lab_unit_id.in_(allowed_lab_unit_ids))
        .count()
    )

    edited_total = (
        db.query(DirectImageUpload.id)
        .filter(DirectImageUpload.lab_unit_id.in_(allowed_lab_unit_ids))
        .filter(DirectImageUpload.edited_filename.isnot(None))
        .count()
    )

    return {
        "encounter": int(encounter_total),
        "direct": int(direct_total),
        "direct_edited": int(edited_total),
    }


def get_missing_pii_counts(db, *, allowed_lab_unit_ids: set[int]) -> dict[str, int]:
    if not allowed_lab_unit_ids:
        return {"encounter": 0, "direct": 0, "direct_edited": 0}

    total = get_total_image_counts(db, allowed_lab_unit_ids=allowed_lab_unit_ids)
    present = get_present_pii_counts(db, allowed_lab_unit_ids=allowed_lab_unit_ids)
    return {
        "encounter": max(0, total["encounter"] - present["encounter"]),
        "direct": max(0, total["direct"] - present["direct"]),
        "direct_edited": max(0, total["direct_edited"] - present["direct_edited"]),
    }


def get_present_metadata_counts(db, *, allowed_lab_unit_ids: set[int]) -> dict[str, int]:
    if not allowed_lab_unit_ids:
        return {"encounter": 0, "direct": 0, "direct_edited": 0}

    encounter_query = (
        db.query(ImageMetadata.id)
        .join(EncounterFile, ImageMetadata.image_uuid == EncounterFile.uuid)
        .join(PatientEncounters, EncounterFile.patient_encounter_id == PatientEncounters.id)
        .join(ZipFile, PatientEncounters.zip_file_id == ZipFile.id)
        .filter(ImageMetadata.image_variant == "orig")
    )
    encounter_query = _apply_lab_unit_scope(encounter_query, allowed_lab_unit_ids)
    encounter_present = encounter_query.count()

    direct_present = (
        db.query(ImageMetadata.id)
        .join(DirectImageUpload, ImageMetadata.image_uuid == DirectImageUpload.uuid)
        .filter(DirectImageUpload.lab_unit_id.in_(allowed_lab_unit_ids))
        .filter(ImageMetadata.image_variant == "orig")
        .count()
    )

    edited_present = (
        db.query(ImageMetadata.id)
        .join(DirectImageUpload, ImageMetadata.image_uuid == DirectImageUpload.uuid)
        .filter(DirectImageUpload.lab_unit_id.in_(allowed_lab_unit_ids))
        .filter(DirectImageUpload.edited_filename.isnot(None))
        .filter(ImageMetadata.image_variant == "edited")
        .count()
    )

    return {
        "encounter": int(encounter_present),
        "direct": int(direct_present),
        "direct_edited": int(edited_present),
    }


def get_present_pii_counts(db, *, allowed_lab_unit_ids: set[int]) -> dict[str, int]:
    if not allowed_lab_unit_ids:
        return {"encounter": 0, "direct": 0, "direct_edited": 0}

    encounter_query = (
        db.query(ImagePiiVerification.id)
        .join(EncounterFile, ImagePiiVerification.image_uuid == EncounterFile.uuid)
        .join(PatientEncounters, EncounterFile.patient_encounter_id == PatientEncounters.id)
        .join(ZipFile, PatientEncounters.zip_file_id == ZipFile.id)
        .filter(ImagePiiVerification.image_variant == "orig")
    )
    encounter_query = _apply_lab_unit_scope(encounter_query, allowed_lab_unit_ids)
    encounter_present = encounter_query.count()

    direct_present = (
        db.query(ImagePiiVerification.id)
        .join(DirectImageUpload, ImagePiiVerification.image_uuid == DirectImageUpload.uuid)
        .filter(DirectImageUpload.lab_unit_id.in_(allowed_lab_unit_ids))
        .filter(ImagePiiVerification.image_variant == "orig")
        .count()
    )

    edited_present = (
        db.query(ImagePiiVerification.id)
        .join(DirectImageUpload, ImagePiiVerification.image_uuid == DirectImageUpload.uuid)
        .filter(DirectImageUpload.lab_unit_id.in_(allowed_lab_unit_ids))
        .filter(DirectImageUpload.edited_filename.isnot(None))
        .filter(ImagePiiVerification.image_variant == "edited")
        .count()
    )

    return {
        "encounter": int(encounter_present),
        "direct": int(direct_present),
        "direct_edited": int(edited_present),
    }


def get_pii_assessed_counts(db, *, allowed_lab_unit_ids: set[int]) -> dict[str, int]:
    if not allowed_lab_unit_ids:
        return {"auto": 0, "manual": 0}
    counts: dict[str, int] = {"auto": 0, "manual": 0}

    encounter_query = (
        db.query(ImagePiiVerification.source, func.count(ImagePiiVerification.id))
        .join(EncounterFile, ImagePiiVerification.image_uuid == EncounterFile.uuid)
        .join(PatientEncounters, EncounterFile.patient_encounter_id == PatientEncounters.id)
        .join(ZipFile, PatientEncounters.zip_file_id == ZipFile.id)
        .filter(ImagePiiVerification.image_variant == "orig")
    )
    encounter_query = _apply_lab_unit_scope(encounter_query, allowed_lab_unit_ids)
    for source, total in encounter_query.group_by(ImagePiiVerification.source).all():
        if source in counts:
            counts[source] += int(total or 0)

    direct_base = (
        db.query(ImagePiiVerification.source, func.count(ImagePiiVerification.id))
        .join(DirectImageUpload, ImagePiiVerification.image_uuid == DirectImageUpload.uuid)
        .filter(DirectImageUpload.lab_unit_id.in_(allowed_lab_unit_ids))
    )
    for source, total in direct_base.filter(ImagePiiVerification.image_variant == "orig").group_by(ImagePiiVerification.source).all():
        if source in counts:
            counts[source] += int(total or 0)
    for source, total in (
        direct_base.filter(ImagePiiVerification.image_variant == "edited")
        .filter(DirectImageUpload.edited_filename.isnot(None))
        .group_by(ImagePiiVerification.source)
        .all()
    ):
        if source in counts:
            counts[source] += int(total or 0)

    return counts


def run_image_metadata_backfill_job(job_id: int) -> None:
    try:
        os.nice(10)
    except Exception:
        pass

    with get_db_session() as db:
        job = db.get(ImageMetadataBackfillJob, job_id)
        if not job or job.status not in {"queued", "running"}:
            return

        allowed_lab_unit_ids: set[int] = set()
        if job.allowed_lab_unit_ids:
            try:
                allowed_lab_unit_ids = set(json.loads(job.allowed_lab_unit_ids))
            except (TypeError, json.JSONDecodeError):
                allowed_lab_unit_ids = set()

        job.status = "running"
        job.started_at = utcnow()
        job.total_candidates = _count_missing_candidates(
            db,
            allowed_lab_unit_ids=allowed_lab_unit_ids,
            run_metadata=job.run_metadata,
            run_pii=job.run_pii,
        )
        job.processed_count = 0
        job.metadata_created_count = 0
        job.pii_created_count = 0
        job.error_count = 0
        job.error_message = None
        db.add(job)
        db.commit()

    processed_since_commit = 0

    def _maybe_commit(db, job_obj):
        nonlocal processed_since_commit
        processed_since_commit += 1
        if processed_since_commit >= 10:
            db.add(job_obj)
            db.commit()
            processed_since_commit = 0

    try:
        with get_db_session() as db:
            job = db.get(ImageMetadataBackfillJob, job_id)
            if not job:
                return
            allowed_lab_unit_ids: set[int] = set()
            if job.allowed_lab_unit_ids:
                try:
                    allowed_lab_unit_ids = set(json.loads(job.allowed_lab_unit_ids))
                except (TypeError, json.JSONDecodeError):
                    allowed_lab_unit_ids = set()

            items = list(_iter_encounter_items(db, allowed_lab_unit_ids=allowed_lab_unit_ids)) + list(
                _iter_direct_items(db, allowed_lab_unit_ids=allowed_lab_unit_ids)
            )
            for item in items:
                if job.requested_limit is not None and job.processed_count >= job.requested_limit:
                    break
                if not item.path.exists():
                    _LOGGER.warning(
                        "Image missing for %s (%s): %s",
                        sanitize_log_value(item.image_uuid),
                        sanitize_log_value(item.image_variant),
                        sanitize_log_value(str(item.path)),
                    )
                    job.error_count += 1
                    job.processed_count += 1
                    _maybe_commit(db, job)
                    time.sleep(_ITEM_SLEEP_SECONDS)
                    continue

                metadata_needed = job.run_metadata and _needs_metadata(db, item.image_uuid, item.image_variant)
                pii_needed = job.run_pii and _needs_pii(db, item.image_uuid, item.image_variant)
                if not metadata_needed and not pii_needed:
                    continue

                try:
                    if metadata_needed:
                        _METADATA_LOGGER.info(
                            "Metadata extract queued for %s (%s)",
                            sanitize_log_value(item.image_uuid),
                            sanitize_log_value(item.image_variant),
                        )
                        meta_result = extract_image_metadata(image_path=item.path)
                        upsert_image_metadata(
                            db,
                            image_uuid=item.image_uuid,
                            image_variant=item.image_variant,
                            encounter_file_id=item.encounter_file_id,
                            direct_image_upload_id=item.direct_image_upload_id,
                            metadata=meta_result,
                        )
                        job.metadata_created_count += 1
                        _METADATA_LOGGER.info(
                            "Metadata extract stored for %s (%s)",
                            sanitize_log_value(item.image_uuid),
                            sanitize_log_value(item.image_variant),
                        )

                    if pii_needed:
                        enqueue_pii_detection_job(
                            db,
                            image_uuid=item.image_uuid,
                            image_variant=item.image_variant,
                            image_path=str(item.path),
                            source="auto",
                        )
                        _LOGGER.info(
                            "PII detection enqueued for %s (%s)",
                            sanitize_log_value(item.image_uuid),
                            sanitize_log_value(item.image_variant),
                        )
                        run_pii_detection_queue(max_jobs=1)
                        db.expire_all()
                        record = (
                            db.query(ImagePiiVerification.id)
                            .filter(
                                ImagePiiVerification.image_uuid == item.image_uuid,
                                ImagePiiVerification.image_variant == item.image_variant,
                            )
                            .first()
                        )
                        if record is not None:
                            job.pii_created_count += 1
                            _LOGGER.info(
                                "PII detection stored for %s (%s)",
                                sanitize_log_value(item.image_uuid),
                                sanitize_log_value(item.image_variant),
                            )
                        time.sleep(_PII_SLEEP_SECONDS)
                except Exception as exc:  # noqa: BLE001
                    job.error_count += 1
                    if metadata_needed:
                        _METADATA_LOGGER.warning(
                            "Metadata extract failed for %s (%s): %s",
                            sanitize_log_value(item.image_uuid),
                            sanitize_log_value(item.image_variant),
                            sanitize_log_value(exc),
                        )
                    if pii_needed:
                        _LOGGER.warning(
                            "PII detection failed for %s (%s): %s",
                            sanitize_log_value(item.image_uuid),
                            sanitize_log_value(item.image_variant),
                            sanitize_log_value(exc),
                        )
                    _LOGGER.warning(
                        "Metadata backfill failed for %s (%s): %s",
                        sanitize_log_value(item.image_uuid),
                        sanitize_log_value(item.image_variant),
                        sanitize_log_value(exc),
                    )

                job.processed_count += 1
                _maybe_commit(db, job)
                time.sleep(_ITEM_SLEEP_SECONDS)

            job.status = "completed"
            job.finished_at = utcnow()
            db.add(job)
            db.commit()
    except Exception as exc:  # noqa: BLE001
        with get_db_session() as db:
            job = db.get(ImageMetadataBackfillJob, job_id)
            if job:
                job.status = "failed"
                job.error_message = str(exc)
                job.finished_at = utcnow()
                db.add(job)
                db.commit()
        _LOGGER.exception(
            "Image metadata backfill job %s failed: %s",
            sanitize_log_value(job_id),
            sanitize_log_value(exc),
        )


def enqueue_image_metadata_backfill(app, job_id: int) -> None:
    executor = app.config.get("EXECUTOR")
    if executor is None:
        return

    def _worker(app_ref, job_id_val: int):
        with app_ref.app_context():
            run_image_metadata_backfill_job(job_id_val)

    executor.submit(_worker, app, job_id)
