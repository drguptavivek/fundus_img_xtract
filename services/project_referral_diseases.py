"""Project-scoped positive disease choices for EncounterSet verification."""

from __future__ import annotations

from dataclasses import dataclass
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Disease, Project, ProjectReferralDisease
from grading_allocation.constants import AllocationScope
from grading_allocation.targets import derive_project_targets


_ENCOUNTER_SET_SCOPES = {
    AllocationScope.DISEASE_ENCOUNTER,
    AllocationScope.ENCOUNTER_SET_UNIFIED,
}


@dataclass(frozen=True)
class ProjectPositiveDiseaseOption:
    """One disease a project permits as a referral-positive finding."""

    disease_id: int
    name: str


def list_project_positive_disease_options(
    db: Session,
    *,
    project_id: int | None,
) -> tuple[ProjectPositiveDiseaseOption, ...]:
    """Return grading targets plus project-configured referral-only diseases."""
    if project_id is None:
        return ()

    diseases: dict[int, str] = {}
    targets, _warnings = derive_project_targets(db, project_id)
    for target in targets:
        if target.identity.scope not in _ENCOUNTER_SET_SCOPES:
            continue
        diseases.update(target.diseases)

    configured_diseases = db.execute(
        select(Disease.id, Disease.name)
        .join(ProjectReferralDisease, ProjectReferralDisease.disease_id == Disease.id)
        .where(
            ProjectReferralDisease.project_id == project_id,
            ProjectReferralDisease.active.is_(True),
        )
    ).all()
    diseases.update({disease_id: name for disease_id, name in configured_diseases})

    return tuple(
        ProjectPositiveDiseaseOption(disease_id=disease_id, name=name)
        for disease_id, name in sorted(
            diseases.items(),
            key=lambda item: (item[1].casefold(), item[0]),
        )
    )


def canonicalize_project_positive_diseases(
    db: Session,
    *,
    project_id: int | None,
    values: list[str] | tuple[str, ...],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Map submitted labels to project schemes and return canonical and invalid values."""
    cleaned_values = tuple(
        value
        for raw_value in values
        if (value := str(raw_value or "").strip())
    )
    options = list_project_positive_disease_options(db, project_id=project_id)
    if not cleaned_values:
        return (), ()

    canonical: list[str] = []
    matched_value_indexes: set[int] = set()
    for option in options:
        disease = db.get(Disease, option.disease_id)
        if disease is None:
            continue
        matching_indexes = {
            index
            for index, value in enumerate(cleaned_values)
            if _value_matches_disease(disease, value)
        }
        if matching_indexes:
            canonical.append(option.name)
            matched_value_indexes.update(matching_indexes)

    invalid = tuple(
        value
        for index, value in enumerate(cleaned_values)
        if index not in matched_value_indexes
    )
    return tuple(canonical), invalid


def list_configured_project_referral_disease_ids(
    db: Session,
    *,
    project_id: int,
) -> tuple[int, ...]:
    """Return explicitly configured referral-only disease IDs for one project."""
    return tuple(
        db.execute(
            select(ProjectReferralDisease.disease_id)
            .where(
                ProjectReferralDisease.project_id == project_id,
                ProjectReferralDisease.active.is_(True),
            )
            .order_by(ProjectReferralDisease.disease_id)
        ).scalars()
    )


def replace_project_referral_diseases(
    db: Session,
    *,
    project_id: int,
    disease_ids: list[int] | tuple[int, ...],
) -> tuple[int, ...]:
    """Replace a project's explicit referral-only disease configuration."""
    if db.get(Project, project_id) is None:
        raise ValueError("Project not found.")

    normalized_ids = tuple(sorted({int(disease_id) for disease_id in disease_ids}))
    existing_disease_ids = set(
        db.execute(select(Disease.id).where(Disease.id.in_(normalized_ids))).scalars()
    ) if normalized_ids else set()
    missing_ids = sorted(set(normalized_ids) - existing_disease_ids)
    if missing_ids:
        raise ValueError(f"Unknown disease ID(s): {', '.join(str(value) for value in missing_ids)}.")

    rows = {
        row.disease_id: row
        for row in db.execute(
            select(ProjectReferralDisease).where(ProjectReferralDisease.project_id == project_id)
        ).scalars()
    }
    selected_ids = set(normalized_ids)
    for disease_id, row in rows.items():
        row.active = disease_id in selected_ids
    for disease_id in selected_ids - rows.keys():
        db.add(ProjectReferralDisease(project_id=project_id, disease_id=disease_id, active=True))
    db.flush()
    return normalized_ids


def _value_matches_disease(disease: Disease, value: str) -> bool:
    normalized = " ".join(value.casefold().split())
    linkage = (disease.remidio_ocr_linkage or "none").casefold()
    if linkage == "dr":
        return normalized == "dr" or "diabetic retinopathy" in normalized
    if linkage == "amd":
        return bool(re.search(r"\bamd\b", normalized)) or "macular degeneration" in normalized
    if linkage == "glaucoma":
        return bool(re.search(r"\bglaucoma\b", normalized))
    return normalized == " ".join(disease.name.casefold().split())
