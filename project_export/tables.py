"""Row builders for the staged export tables.

Each builder takes the SQLAlchemy session and an :class:`ExportScope` (a
``project_sync.dto.SyncContext`` satisfies the same interface) and returns
dict rows keyed by the column names in ``schema``. Scoping and identifier
rules are reused from ``project_sync.inventory`` so the export and the sync
API can never disagree about who may see what.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from functools import cached_property
from typing import Iterator

from sqlalchemy import select

from models import (
    DirectImageUpload,
    Disease,
    ImageMetadata,
    LabUnit,
    PatientEncounters,
)
from iitk_api_integration.models import IITKApiSessionLink
from remidio_api_integration.models import RemidioApiExamEncounter
from project_sync.inventory import (
    KIND_DIRECT_IMAGE,
    KIND_ENCOUNTER_FILE,
    KIND_ENCOUNTER_FILE_PDF,
    KIND_ENCOUNTER_SET_IMAGE,
    _collect_encounter_media,
    _load_task_bundles,
    _encounter_scope,
    _media_item,
    _pii_detected_uuids,
    _sanitize_encounter_metadata,
)


@dataclass(frozen=True)
class ExportScope:
    """Who the package is for: one project, the labs in scope, and the labs that may see identifiers."""

    project_id: int | None  # None = encounters that belong to no project
    lab_unit_ids: frozenset[int]
    pii_lab_unit_ids: frozenset[int] = frozenset()

    def allows_pii(self, lab_unit_id: int | None) -> bool:
        return lab_unit_id is not None and lab_unit_id in self.pii_lab_unit_ids


def _chunks(values: list, size: int = 1000) -> Iterator[list]:
    for start in range(0, len(values), size):
        yield values[start:start + size]


def ts(value) -> datetime | None:
    """Datetime or ISO string -> datetime; anything unparseable -> None (never fail an export on a bad timestamp)."""
    if value is None or isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


_FILE_NAME = re.compile(r"[^\"'/\\<>:|?*\r\n]{1,120}?\.(?:jpe?g|png|tiff?|bmp|gif|webp|pdf|zip)\b", re.IGNORECASE)


def redact_files(text, pii: bool):
    """System-generated error text often quotes the uploaded file's name; mask it without an identifiers grant."""
    if pii or not text:
        return text
    return _FILE_NAME.sub("[file]", str(text))


def drop_keys(value, keys: frozenset[str]):
    """Copy of a nested JSON value without the given dict keys at any depth."""
    if isinstance(value, dict):
        return {k: drop_keys(v, keys) for k, v in value.items() if k not in keys}
    if isinstance(value, list):
        return [drop_keys(v, keys) for v in value]
    return value


@dataclass
class BuildContext:
    """Shared, lazily loaded inputs for the stage builders of one export."""

    db: object
    scope: "ExportScope"
    encounters: list
    media: dict  # encounter id -> [(kind, row)]

    @cached_property
    def encounter_by_id(self) -> dict:
        return {e.id: e for e in self.encounters}

    @cached_property
    def encounter_uuid(self) -> dict:
        return {e.id: e.uuid for e in self.encounters}

    def allows_pii(self, encounter_id) -> bool:
        encounter = self.encounter_by_id.get(encounter_id)
        return bool(encounter) and self.scope.allows_pii(encounter.lab_unit_id)

    @cached_property
    def image_uuid_by_row(self) -> dict:
        """(kind, row id) -> uuid for every exported encounter image."""
        return {(kind, row.id): row.uuid for items in self.media.values() for kind, row in items}

    @cached_property
    def direct_uploads(self) -> list:
        """Direct uploads in scope (PII-detected ones included; they carry a flag)."""
        return self.db.execute(
            select(DirectImageUpload).where(
                DirectImageUpload.project_id == self.scope.project_id,
                DirectImageUpload.lab_unit_id.in_(list(self.scope.lab_unit_ids)),
            ).order_by(DirectImageUpload.id)
        ).scalars().all()

    @cached_property
    def pii_detected_uuids(self) -> set:
        """Image uuids the PII scan flagged."""
        uuids = [row.uuid for items in self.media.values() for _, row in items if row.uuid]
        uuids += [row.uuid for row in self.direct_uploads]
        detected: set = set()
        for chunk in _chunks(uuids):
            detected |= set(_pii_detected_uuids(self.db, chunk))
        return detected

    @cached_property
    def bundles(self) -> list:
        """Tasks with grades and consensus for the exported encounters and images (annotation counts, not geometry)."""
        file_ids = [row.id for items in self.media.values() for kind, row in items if kind == KIND_ENCOUNTER_FILE]
        set_ids = [row.id for items in self.media.values() for kind, row in items if kind == KIND_ENCOUNTER_SET_IMAGE]
        return _load_task_bundles(
            self.db, self.scope, encounter_ids=[e.id for e in self.encounters], file_ids=file_ids,
            set_image_ids=set_ids, direct_ids=[row.id for row in self.direct_uploads], with_annotations=False,
        )

    cache: dict = field(default_factory=dict)


def _json(value) -> str | None:
    return None if value is None else json.dumps(value, ensure_ascii=False, default=str)


def load_encounters(db, scope) -> list[PatientEncounters]:
    return db.execute(
        select(PatientEncounters).where(*_encounter_scope(scope)).order_by(PatientEncounters.id)
    ).scalars().all()


def _source_paths(db, scope) -> dict[int, str]:
    """remidio_api / iitk_api / remidio_zip / other for every in-scope encounter."""
    in_scope = _encounter_scope(scope)
    api = set(db.execute(
        select(RemidioApiExamEncounter.patient_encounter_id)
        .join(PatientEncounters, PatientEncounters.id == RemidioApiExamEncounter.patient_encounter_id)
        .where(*in_scope)
    ).scalars())
    iitk = set(db.execute(
        select(IITKApiSessionLink.patient_encounter_id)
        .join(PatientEncounters, PatientEncounters.id == IITKApiSessionLink.patient_encounter_id)
        .where(*in_scope)
    ).scalars())
    zipped = set(db.execute(
        select(PatientEncounters.id).where(*in_scope, PatientEncounters.zip_file_id.is_not(None))
    ).scalars())
    paths: dict[int, str] = {}
    for encounter_id in api | iitk | zipped:
        paths[encounter_id] = "remidio_api" if encounter_id in api else "iitk_api" if encounter_id in iitk else "remidio_zip"
    return paths


def encounter_rows(ctx: BuildContext) -> list[dict]:
    db, scope, encounters, media = ctx.db, ctx.scope, ctx.encounters, ctx.media
    disease_names = dict(db.execute(select(Disease.id, Disease.name)).all())
    lab_names = dict(db.execute(select(LabUnit.id, LabUnit.name)).all())
    sources = _source_paths(db, scope)
    rows = []
    for encounter in encounters:
        pii = scope.allows_pii(encounter.lab_unit_id)
        patient = (encounter.metadata_json or {}).get("patient") or {}
        rows.append({
            "encounter_uuid": encounter.uuid,
            "project_id": encounter.project_id,
            "lab_unit_id": encounter.lab_unit_id,
            "lab_unit_name": lab_names.get(encounter.lab_unit_id),
            "disease": disease_names.get(encounter.disease_id),
            "source_path": sources.get(encounter.id, "other"),
            "upload_profile_id": encounter.upload_profile_id,
            "capture_date": encounter.capture_date_dt,
            "is_set_based": bool(encounter.is_set_based),
            "image_count": len(media.get(encounter.id, [])),
            "referral_suggestion": encounter.referral_suggestion,
            "referral_positive_diseases": _json(encounter.referral_positive_diseases_json),
            "identifiers_included": pii,
            "patient_id": encounter.patient_id if pii else None,
            "patient_name": encounter.name if pii else None,
            "sex": patient.get("sex"),
            "patient_age_years": patient.get("patient_age_yrs"),
            "date_of_birth": patient.get("patient_dob") if pii else None,
            "mrn": patient.get("hospital_UHID") if pii else None,
            "remarks": encounter.remarks,
            "metadata": _json(_sanitize_encounter_metadata(encounter.metadata_json, pii=pii)),
        })
    return rows


def _image_properties(db, uuids: list[str]) -> dict[str, ImageMetadata]:
    props: dict[str, ImageMetadata] = {}
    for chunk in _chunks(uuids):
        for row in db.execute(
            select(ImageMetadata).where(ImageMetadata.image_uuid.in_(chunk), ImageMetadata.image_variant == "orig")
        ).scalars():
            props[row.image_uuid] = row
    return props


def image_rows(ctx: BuildContext) -> list[dict]:
    db, scope, encounters, media = ctx.db, ctx.scope, ctx.encounters, ctx.media
    by_id = {encounter.id: encounter for encounter in encounters}
    entries = []  # (encounter_uuid, lab_unit_id, kind, row, pii)
    for encounter_id, items in media.items():
        encounter = by_id[encounter_id]
        pii = scope.allows_pii(encounter.lab_unit_id)
        entries.extend((encounter.uuid, encounter.lab_unit_id, kind, row, pii) for kind, row in items)
    entries.extend(
        (None, row.lab_unit_id, KIND_DIRECT_IMAGE, row, scope.allows_pii(row.lab_unit_id)) for row in ctx.direct_uploads
    )
    props = _image_properties(db, [row.uuid for *_, row, _ in entries])
    rows = []
    for encounter_uuid, lab_unit_id, kind, row, pii in entries:
        item = _media_item(kind, row, fingerprint=None, pii=pii)
        prop = props.get(row.uuid)
        rows.append({
            "image_uuid": row.uuid,
            "kind": kind,
            "encounter_uuid": encounter_uuid,
            "lab_unit_id": lab_unit_id,
            "spatial_position": item.get("position"),
            "ext": item.get("ext"),
            "source_md5": item.get("source_md5"),
            "created_at": getattr(row, "created_at", None),
            "is_pii": bool(item.get("is_pii")),
            "pii_detected": row.uuid in ctx.pii_detected_uuids,
            "has_edited": bool(item.get("has_edited")),
            "original_filename": getattr(row, "original_filename", None) if pii else None,
            "width": prop.width if prop else None,
            "height": prop.height if prop else None,
            "format": prop.format if prop else None,
            "file_size_bytes": prop.file_size_bytes if prop else None,
            "remarks": getattr(row, "remarks", None),
            "metadata": _json(item.get("metadata")),
        })
    return rows


class _AllImages:
    """Scope view that lets the inventory loader return PII-flagged images too (rows only, never files)."""

    def __init__(self, scope):
        self.project_id = scope.project_id
        self.lab_unit_ids = scope.lab_unit_ids

    @staticmethod
    def allows_pii(_lab_unit_id) -> bool:
        return True


def collect_media(db, scope, encounters):
    """Image rows per encounter. PII-flagged images are included (they carry a flag); report PDFs need a grant."""
    media = _collect_encounter_media(db, _AllImages(scope), encounters)
    by_id = {e.id: e for e in encounters}
    return {
        encounter_id: [
            (kind, row) for kind, row in items
            if kind != KIND_ENCOUNTER_FILE_PDF or scope.allows_pii(by_id[encounter_id].lab_unit_id)
        ]
        for encounter_id, items in media.items()
    }
