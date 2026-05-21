"""Encounter-set asset classification helpers."""
from __future__ import annotations

from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from models import EncounterSetImage

ASSET_KIND_CLINICAL_IMAGE = "clinical_image"
ASSET_KIND_DOCUMENT = "document"
ASSET_KIND_PDF = "pdf"
ASSET_KIND_DOCUMENT_IMAGE = "document_image"

SUPPORTING_ASSET_KINDS = frozenset(
    {
        ASSET_KIND_DOCUMENT,
        ASSET_KIND_PDF,
        ASSET_KIND_DOCUMENT_IMAGE,
    }
)
ALL_ASSET_KINDS = frozenset({ASSET_KIND_CLINICAL_IMAGE, *SUPPORTING_ASSET_KINDS})


def clinical_task_image_query(db: OrmSession, patient_encounter_id: int):
    """Return the explicit task-evidence query for encounter-set clinical images."""
    return (
        db.query(EncounterSetImage)
        .filter(
            EncounterSetImage.patient_encounter_id == patient_encounter_id,
            EncounterSetImage.asset_kind == ASSET_KIND_CLINICAL_IMAGE,
            EncounterSetImage.creates_task.is_(True),
            EncounterSetImage.visible_to_grader.is_(True),
        )
        .order_by(EncounterSetImage.spatial_position)
    )


def list_clinical_task_images(db: OrmSession, patient_encounter_id: int) -> list[EncounterSetImage]:
    """List encounter-set images that are eligible to be included in grading task evidence."""
    return clinical_task_image_query(db, patient_encounter_id).all()


def clinical_task_image_ids(db: OrmSession, patient_encounter_id: int) -> list[int]:
    """Return only IDs for task-eligible clinical images."""
    return list(
        db.execute(
            select(EncounterSetImage.id)
            .where(
                EncounterSetImage.patient_encounter_id == patient_encounter_id,
                EncounterSetImage.asset_kind == ASSET_KIND_CLINICAL_IMAGE,
                EncounterSetImage.creates_task.is_(True),
                EncounterSetImage.visible_to_grader.is_(True),
            )
            .order_by(EncounterSetImage.spatial_position)
        ).scalars()
    )


def normalize_supporting_asset_kind(value: str) -> str:
    asset_kind = (value or "").strip().lower()
    if asset_kind not in SUPPORTING_ASSET_KINDS:
        allowed = ", ".join(sorted(SUPPORTING_ASSET_KINDS))
        raise ValueError(f"asset_kind must be one of: {allowed}")
    return asset_kind


def all_are_supporting_asset_kinds(values: Iterable[str]) -> bool:
    return all((value or "").strip().lower() in SUPPORTING_ASSET_KINDS for value in values)
