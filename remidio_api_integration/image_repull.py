"""Restore full-fidelity Remidio images that the old lossy metadata strip re-encoded.

Remidio file links are signed and expire, so the stored ``remidio_path`` cannot be reused. For each
exam site/date the Remidio API is asked for the exams again (fresh links), the damaged images are
downloaded, stripped losslessly and written over the existing file. Nothing in the database is
written: no OCR, no metadata, no new rows. A file is "damaged" when its JPEG header still carries the
quality-75 signature, so the job is idempotent and a re-run only touches what is left.
See docs/API/remidio-image-repull/README.md.
"""
from __future__ import annotations

import json
import logging
import os
import time
from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time as clock, timedelta, timezone
from io import BytesIO
from pathlib import Path

from PIL import Image
from sqlalchemy import select

from db_transaction_manager import get_db_session
from auth.utils import utcnow
from models import BASE_DIR, EncounterSetImage, RemidioConnection, RemidioExam, RemidioImage
from utils.image_processing import has_default_quality_75_tables, strip_exif_data
from utils.log_sanitize import sanitize_log_value

from .client import RemidioClient
from .errors import RemidioIntegrationError
from .service import _secrets
from .validation import extract_exam_payloads, normalize_date, require_list_data

LOGGER = logging.getLogger(__name__)

HEADER_BYTES = 4096
DEFAULT_BATCH_IMAGES = 50
PAUSE_BETWEEN_API_CALLS_SECONDS = float(os.getenv("REMIDIO_REPULL_PAUSE_SECONDS", "2.5"))
PAUSE_BETWEEN_DOWNLOADS_SECONDS = float(os.getenv("REMIDIO_REPULL_DOWNLOAD_PAUSE_SECONDS", "1.0"))
PAUSE_BETWEEN_ENCOUNTERS_SECONDS = float(os.getenv("REMIDIO_REPULL_ENCOUNTER_PAUSE_SECONDS", "10"))


# One JSON line per restored image: the durable record of what was healed (line count = images restored).
RESTORE_LOG = Path(os.getenv("REMIDIO_REPULL_LOG", str(BASE_DIR / "logs" / "remidio_image_repull.jsonl")))


@dataclass(frozen=True)
class Candidate:
    remidio_image_id: str
    path: Path
    encounter_id: int = 0


@dataclass
class RepullSummary:
    groups: int = 0
    candidates: int = 0
    replaced: int = 0
    already_ok: int = 0
    missing_file: int = 0
    not_returned_by_source: int = 0
    source_is_quality_75: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)
    next_before: str | None = None  # exam date cursor: pass back as ``before`` for the next batch
    done: bool = False

    def as_dict(self) -> dict:
        return asdict(self)


def repull_batch(
    *,
    limit_images: int = DEFAULT_BATCH_IMAGES,
    before: date | None = None,
    dry_run: bool = False,
    pause: bool = True,
) -> RepullSummary:
    """Repair about ``limit_images`` damaged images (whole days at a time), newest exams first, older than ``before``."""
    summary = RepullSummary()
    groups = _damaged_groups(limit_images=max(1, limit_images), before=before, summary=summary)
    summary.groups = len(groups)
    summary.done = not groups
    if dry_run or not groups:
        return summary

    clients: dict[int, RemidioClient] = {}
    for (connection_id, site, exam_day), candidates in groups.items():
        try:
            fresh = _fresh_image_urls(clients, connection_id, site, exam_day)
        except Exception as exc:  # noqa: BLE001 - one site/day failing must not stop the batch
            summary.failed += len(candidates)
            summary.errors.append(f"{site} {exam_day}: {sanitize_log_value(exc)}"[:300])
            summary.next_before = exam_day.isoformat()
            continue
        if pause:
            time.sleep(PAUSE_BETWEEN_API_CALLS_SECONDS)
        previous_encounter = None
        for candidate in sorted(candidates, key=lambda item: item.encounter_id):
            if pause and previous_encounter is not None and candidate.encounter_id != previous_encounter:
                time.sleep(PAUSE_BETWEEN_ENCOUNTERS_SECONDS)  # a pause between encounters, on top of the per-download one
            previous_encounter = candidate.encounter_id
            _repair_one(clients[connection_id], candidate, fresh.get(candidate.remidio_image_id), summary)
            if pause:
                time.sleep(PAUSE_BETWEEN_DOWNLOADS_SECONDS)
        summary.next_before = exam_day.isoformat()
    return summary


def _damaged_groups(*, limit_images: int, before: date | None, summary: RepullSummary) -> "OrderedDict[tuple, list[Candidate]]":
    """Newest-first (connection, site, day) groups of images whose stored file is still quality-75."""
    groups: OrderedDict[tuple, list[Candidate]] = OrderedDict()
    found = 0
    with get_db_session() as db:
        statement = (
            select(
                RemidioImage.remidio_image_id,
                RemidioExam.remidio_connection_id,
                RemidioExam.site_custom_identifier,
                RemidioExam.exam_date,
                EncounterSetImage.folder_rel,
                EncounterSetImage.original_filename,
                EncounterSetImage.patient_encounter_id,
            )
            .join(RemidioExam, RemidioExam.id == RemidioImage.remidio_exam_id)
            .join(EncounterSetImage, EncounterSetImage.id == RemidioImage.encounter_set_image_id)
            .where(RemidioExam.exam_date.is_not(None), RemidioExam.site_custom_identifier.is_not(None))
            .order_by(RemidioExam.exam_date.desc(), RemidioImage.id)
        )
        if before is not None:
            statement = statement.where(RemidioExam.exam_date < datetime.combine(before, clock.min, tzinfo=timezone.utc))
        current_day = None
        for image_id, connection_id, site, exam_date, folder_rel, filename, encounter_id in db.execute(statement).yield_per(2000):
            key = (connection_id, site, exam_date.date())
            if found >= limit_images and key[2] != current_day:
                break  # finish the whole day (every site) being collected, then stop: ``before`` is a day cursor
            path = BASE_DIR / folder_rel / filename
            try:
                with open(path, "rb") as handle:
                    head = handle.read(HEADER_BYTES)
            except OSError:
                summary.missing_file += 1
                continue
            if not has_default_quality_75_tables(head):
                summary.already_ok += 1
                continue
            groups.setdefault(key, []).append(Candidate(str(image_id), path, encounter_id))
            summary.candidates += 1
            found += 1
            current_day = key[2]
    return groups


def _fresh_image_urls(clients: dict[int, RemidioClient], connection_id: int, site: str, exam_day: date) -> dict[str, str]:
    """image id -> freshly signed download URL for every image Remidio reports on that site/day."""
    with get_db_session() as db:
        if connection_id not in clients:
            clients[connection_id] = RemidioClient(_secrets(db.get(RemidioConnection, connection_id)))
    # Exam timestamps are stored in UTC while Remidio buckets by local day: ask for the day either side.
    start, end = (normalize_date((exam_day + timedelta(days=offset)).isoformat()) for offset in (-1, 1))
    body = clients[connection_id].get_exams_by_date(
        start_date=start, end_date=end, site_custom_identifier=site, include_file_paths=True,
    )
    payloads = extract_exam_payloads(require_list_data(body), site_custom_identifier=site, pull_source="getExamsByDate")
    return {
        image.remidio_image_id: image.remidio_path
        for payload in payloads
        for image in payload.images
        if image.remidio_path
    }


def _repair_one(client: RemidioClient, candidate: Candidate, url: str | None, summary: RepullSummary) -> None:
    if not url:
        summary.not_returned_by_source += 1
        return
    try:
        content, _content_type = client.download_file(url)
        if has_default_quality_75_tables(content[:HEADER_BYTES]):
            summary.source_is_quality_75 += 1  # the source itself is quality 75: nothing better to restore
            return
        clean = strip_exif_data(content)
        with Image.open(BytesIO(clean)) as image:
            image.verify()
        bytes_before = candidate.path.stat().st_size if candidate.path.exists() else None
        _replace_file(candidate.path, clean)
        summary.replaced += 1
        _log_restored(candidate, bytes_before, len(clean), len(content))
    except (OSError, RemidioIntegrationError, Image.UnidentifiedImageError, SyntaxError) as exc:
        summary.failed += 1
        summary.errors.append(f"{candidate.remidio_image_id}: {sanitize_log_value(exc)}"[:300])
        LOGGER.warning("Remidio image re-pull failed image=%s error=%s", candidate.remidio_image_id, sanitize_log_value(exc))


def _log_restored(candidate: Candidate, bytes_before: int | None, bytes_after: int, bytes_downloaded: int) -> None:
    LOGGER.info(
        "Remidio image restored image=%s encounter=%s path=%s bytes %s -> %s",
        sanitize_log_value(candidate.remidio_image_id), candidate.encounter_id,
        sanitize_log_value(candidate.path), bytes_before, bytes_after,
    )
    record = {
        "at_utc": utcnow().isoformat(), "remidio_image_id": candidate.remidio_image_id,
        "encounter_id": candidate.encounter_id, "path": str(candidate.path),
        "bytes_before": bytes_before, "bytes_downloaded": bytes_downloaded, "bytes_after": bytes_after,
    }
    try:
        RESTORE_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(RESTORE_LOG, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")
    except OSError as exc:  # the log is a convenience: never fail a restored image over it
        LOGGER.warning("Could not append to %s: %s", RESTORE_LOG, sanitize_log_value(exc))


def _replace_file(path: Path, data: bytes) -> None:
    """Atomic overwrite: a reader sees the old or the new file, never a partial one."""
    temp = path.with_name(f".{path.name}.repull")
    temp.write_bytes(data)
    os.replace(temp, path)
