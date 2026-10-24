"""Restore full-fidelity IITK images that the old lossy metadata strip re-encoded.

IITK images are fetched by session id and source filename (both kept on the session link and the image
metadata), so no signed links are involved. Damaged images - stored files whose JPEG header still carries
the quality-75 signature - are downloaded again, stripped losslessly and written over the existing file.
Nothing in the database is written: no OCR, no metadata, no PII scan, no new rows. The job is idempotent.
See docs/API/iitk-image-repull/README.md.
"""
from __future__ import annotations

import json
import logging
import os
import random
import time
from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from datetime import date
from io import BytesIO
from pathlib import Path

from PIL import Image
from sqlalchemy import select

from auth.utils import utcnow
from db_transaction_manager import get_db_session
from models import BASE_DIR, EncounterSetImage, PatientEncounters
from remidio_api_integration.image_repull import HEADER_BYTES, _replace_file
from utils.encryption import decrypt_password_with_salt
from utils.image_processing import has_default_quality_75_tables, strip_exif_data
from utils.log_sanitize import sanitize_log_value

from .client import IITKClient
from .errors import IITKIntegrationError
from .models import IITKApiProjectConfig, IITKApiSessionLink
from .service import POSITION_ORDER

LOGGER = logging.getLogger(__name__)

DEFAULT_BATCH_IMAGES = 50
PAUSE_BETWEEN_DOWNLOADS_SECONDS = float(os.getenv("IITK_REPULL_DOWNLOAD_PAUSE_SECONDS", "1.0"))
# A random gap between encounters (not a fixed beat) keeps the load on the provider irregular.
ENCOUNTER_PAUSE_RANGE_SECONDS = (
    float(os.getenv("IITK_REPULL_ENCOUNTER_PAUSE_MIN_SECONDS", "3")),
    float(os.getenv("IITK_REPULL_ENCOUNTER_PAUSE_MAX_SECONDS", "8")),
)

# One JSON line per restored image: the durable record of what was healed (line count = images restored).
RESTORE_LOG = Path(os.getenv("IITK_REPULL_LOG", str(BASE_DIR / "logs" / "iitk_image_repull.jsonl")))


@dataclass(frozen=True)
class Candidate:
    image_id: int
    encounter_id: int
    config_id: int
    session_id: str
    spatial_position: int
    source_filename: str | None
    source_size_bytes: int | None
    path: Path


@dataclass
class RepullSummary:
    encounters: int = 0
    candidates: int = 0
    replaced: int = 0
    already_ok: int = 0
    missing_file: int = 0
    not_returned_by_source: int = 0
    source_changed: int = 0  # size differs from what was synced: a normal resync owns that image
    source_is_quality_75: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)
    next_before: str | None = None  # capture date cursor: pass back as ``before`` for the next batch
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
    """Repair about ``limit_images`` damaged images (whole capture days at a time), newest first, older than ``before``."""
    summary = RepullSummary()
    encounters = _damaged_encounters(limit_images=max(1, limit_images), before=before, summary=summary)
    summary.encounters = len(encounters)
    summary.done = not encounters
    if dry_run or not encounters:
        return summary

    clients: dict[int, IITKClient] = {}
    inventories: dict[str, dict[int, str]] = {}
    previous_encounter = None
    for (encounter_id, capture_day), candidates in encounters.items():
        if pause and previous_encounter is not None:
            time.sleep(random.uniform(*ENCOUNTER_PAUSE_RANGE_SECONDS))
        previous_encounter = encounter_id
        for candidate in candidates:
            _repair_one(_client(clients, candidate.config_id), candidate, inventories, summary)
            if pause:
                time.sleep(PAUSE_BETWEEN_DOWNLOADS_SECONDS)
        summary.next_before = capture_day.isoformat()
    return summary


def _damaged_encounters(*, limit_images: int, before: date | None, summary: RepullSummary) -> "OrderedDict[tuple, list[Candidate]]":
    """Newest-first (encounter, capture day) groups of IITK images whose stored file is still quality-75."""
    groups: OrderedDict[tuple, list[Candidate]] = OrderedDict()
    found = 0
    with get_db_session() as db:
        statement = (
            select(EncounterSetImage, IITKApiSessionLink, PatientEncounters.capture_date_dt)
            .join(IITKApiSessionLink, IITKApiSessionLink.patient_encounter_id == EncounterSetImage.patient_encounter_id)
            .join(PatientEncounters, PatientEncounters.id == EncounterSetImage.patient_encounter_id)
            .where(PatientEncounters.capture_date_dt.is_not(None), EncounterSetImage.asset_kind == "clinical_image")
            .order_by(PatientEncounters.capture_date_dt.desc(), EncounterSetImage.patient_encounter_id.desc(), EncounterSetImage.spatial_position)
        )
        if before is not None:
            statement = statement.where(PatientEncounters.capture_date_dt < before)
        current_day = None
        for image, link, capture_day in db.execute(statement).yield_per(2000):
            if found >= limit_images and capture_day != current_day:
                break  # finish the whole day being collected, then stop: ``before`` is a day cursor
            path = BASE_DIR / image.folder_rel / image.original_filename
            try:
                with open(path, "rb") as handle:
                    head = handle.read(HEADER_BYTES)
            except OSError:
                summary.missing_file += 1
                continue
            if not has_default_quality_75_tables(head):
                summary.already_ok += 1
                continue
            meta = image.metadata_json or {}
            groups.setdefault((image.patient_encounter_id, capture_day), []).append(Candidate(
                image.id, image.patient_encounter_id, link.config_id, link.source_session_id, image.spatial_position,
                meta.get("source_filename"), meta.get("source_size_bytes"), path,
            ))
            summary.candidates += 1
            found += 1
            current_day = capture_day
    return groups


def _client(clients: dict[int, IITKClient], config_id: int) -> IITKClient:
    if config_id not in clients:
        with get_db_session() as db:
            row = db.get(IITKApiProjectConfig, config_id)
            token = decrypt_password_with_salt(row.api_token_encrypted, row.secret_salt)
            clients[config_id] = IITKClient(token, base_url=row.base_url)
    return clients[config_id]


def _source_filename(client: IITKClient, candidate: Candidate, inventories: dict[str, dict[int, str]]) -> str | None:
    """The synced filename, or - for rows that never recorded one - the provider's current name for that position."""
    if candidate.source_filename:
        return candidate.source_filename
    if candidate.session_id not in inventories:
        inventory = client.list_images(candidate.session_id)
        inventories[candidate.session_id] = {
            POSITION_ORDER[image.position]: image.filename for image in inventory.images if image.position in POSITION_ORDER
        }
    return inventories[candidate.session_id].get(candidate.spatial_position)


def _repair_one(client: IITKClient, candidate: Candidate, inventories: dict, summary: RepullSummary) -> None:
    try:
        filename = _source_filename(client, candidate, inventories)
        if not filename:
            summary.not_returned_by_source += 1
            return
        content = client.get_image(candidate.session_id, filename)
        if candidate.source_size_bytes is not None and len(content) != candidate.source_size_bytes:
            summary.source_changed += 1
            return
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
    except (OSError, IITKIntegrationError, Image.UnidentifiedImageError, SyntaxError) as exc:
        summary.failed += 1
        summary.errors.append(f"{candidate.image_id}: {sanitize_log_value(exc)}"[:300])
        LOGGER.warning("IITK image re-pull failed image=%s error=%s", candidate.image_id, sanitize_log_value(exc))


def _log_restored(candidate: Candidate, bytes_before: int | None, bytes_after: int, bytes_downloaded: int) -> None:
    LOGGER.info(
        "IITK image restored image=%s encounter=%s path=%s bytes %s -> %s",
        candidate.image_id, candidate.encounter_id, sanitize_log_value(candidate.path), bytes_before, bytes_after,
    )
    record = {
        "at_utc": utcnow().isoformat(), "encounter_set_image_id": candidate.image_id,
        "encounter_id": candidate.encounter_id, "path": str(candidate.path),
        "bytes_before": bytes_before, "bytes_downloaded": bytes_downloaded, "bytes_after": bytes_after,
    }
    try:
        RESTORE_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(RESTORE_LOG, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")
    except OSError as exc:  # the log is a convenience: never fail a restored image over it
        LOGGER.warning("Could not append to %s: %s", RESTORE_LOG, sanitize_log_value(exc))
