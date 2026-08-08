"""Project-scoped positive disease choices for EncounterSet verification."""

from __future__ import annotations

from dataclasses import dataclass
import re

from sqlalchemy.orm import Session

from grading_allocation.constants import AllocationScope
from grading_allocation.targets import derive_project_targets
from models import Disease


_ENCOUNTER_SET_SCOPES = {
    AllocationScope.DISEASE_ENCOUNTER,
    AllocationScope.ENCOUNTER_SET_UNIFIED,
}


@dataclass(frozen=True)
class ProjectPositiveDiseaseOption:
    """One image grading scheme that can classify a project EncounterSet."""

    disease_id: int
    name: str


def list_project_positive_disease_options(
    db: Session,
    *,
    project_id: int | None,
) -> tuple[ProjectPositiveDiseaseOption, ...]:
    """Return image grading scheme names available to EncounterSets in a project."""
    if project_id is None:
        return ()

    diseases: dict[int, str] = {}
    targets, _warnings = derive_project_targets(db, project_id)
    for target in targets:
        if target.identity.scope not in _ENCOUNTER_SET_SCOPES:
            continue
        diseases.update(target.diseases)

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
