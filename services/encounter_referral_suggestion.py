"""Encounter-level referral suggestion derivation."""

from __future__ import annotations

from typing import Any, Iterable

from sqlalchemy.orm import Session

from auth.utils import utcnow
from encounter_sets.models import EncounterSetAttachment
from models import PatientEncounters


REFERRAL_SUGGESTION_YES = "yes"
REFERRAL_SUGGESTION_NO = "no"
REFERRAL_SUGGESTION_MISSING = "missing"
REFERRAL_SUGGESTION_VALUES = {
    REFERRAL_SUGGESTION_YES,
    REFERRAL_SUGGESTION_NO,
    REFERRAL_SUGGESTION_MISSING,
}
def normalize_referral_suggestion(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in REFERRAL_SUGGESTION_VALUES:
        return normalized
    return REFERRAL_SUGGESTION_MISSING


def derive_referral_suggestion_from_attachment_metadata(metadata_items: Iterable[dict[str, Any]]) -> str:
    has_no = False
    for metadata in metadata_items:
        suggestion = _metadata_referral_suggestion(metadata or {})
        if suggestion == REFERRAL_SUGGESTION_YES:
            return REFERRAL_SUGGESTION_YES
        if suggestion == REFERRAL_SUGGESTION_NO:
            has_no = True
    return REFERRAL_SUGGESTION_NO if has_no else REFERRAL_SUGGESTION_MISSING


def normalize_referral_positive_diseases(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw_values = [item.strip() for item in value.replace(";", ",").split(",")]
    elif isinstance(value, Iterable):
        raw_values = []
        for item in value:
            raw_values.extend(part.strip() for part in str(item).replace(";", ",").split(","))
    else:
        raw_values = [str(value).strip()]
    normalized: list[str] = []
    for item in raw_values:
        label = " ".join(item.split())
        if label and label.casefold() not in {existing.casefold() for existing in normalized}:
            normalized.append(label)
    return normalized


def derive_referral_positive_diseases_from_attachment_metadata(metadata_items: Iterable[dict[str, Any]]) -> list[str]:
    positive: list[str] = []
    for metadata in metadata_items:
        for code in _metadata_positive_diseases(metadata or {}):
            if code not in positive:
                positive.append(code)
    return positive


def update_encounter_referral_suggestion_from_attachments(
    db: Session,
    encounter_id: int,
    *,
    preserve_existing_when_missing: bool = False,
) -> str:
    encounter = db.get(PatientEncounters, encounter_id)
    if encounter is None:
        return REFERRAL_SUGGESTION_MISSING

    attachments = (
        db.query(EncounterSetAttachment.metadata_json)
        .filter(EncounterSetAttachment.patient_encounter_id == encounter_id)
        .all()
    )
    suggestion = derive_referral_suggestion_from_attachment_metadata(metadata for (metadata,) in attachments)
    positive_diseases = derive_referral_positive_diseases_from_attachment_metadata(metadata for (metadata,) in attachments)
    if encounter.project_id is not None and positive_diseases:
        # Keep raw provider evidence on the attachment, while persisting only
        # the project's grading or explicitly configured referral diseases.
        from verify_encounter_set.project_disease_options import (
            canonicalize_project_positive_diseases,
        )

        canonical_diseases, _unsupported_diseases = canonicalize_project_positive_diseases(
            db,
            project_id=encounter.project_id,
            values=positive_diseases,
        )
        positive_diseases = list(canonical_diseases)
    if (
        preserve_existing_when_missing
        and suggestion == REFERRAL_SUGGESTION_MISSING
        and encounter.referral_suggestion in {REFERRAL_SUGGESTION_YES, REFERRAL_SUGGESTION_NO}
    ):
        return encounter.referral_suggestion
    encounter.referral_suggestion = suggestion
    encounter.referral_suggestion_updated_at = utcnow()
    encounter.referral_positive_diseases_json = positive_diseases
    db.add(encounter)
    db.flush()
    return suggestion


def _metadata_positive_diseases(metadata: dict[str, Any]) -> list[str]:
    values = {
        "DR": _ocr_text_suggestion(_nested(metadata, "ocr", "dr_report", "dr_data", "result"), disease="dr"),
        "AMD": _ocr_text_suggestion(_nested(metadata, "ocr", "amd_report", "amd_data", "result"), disease="amd"),
        "Glaucoma": _ocr_text_suggestion(_nested(metadata, "ocr", "glaucoma_report", "glaucoma_data", "result"), disease="glaucoma"),
    }
    return [code for code, suggestion in values.items() if suggestion == REFERRAL_SUGGESTION_YES]


def _metadata_referral_suggestion(metadata: dict[str, Any]) -> str:
    values = [
        _bool_suggestion(metadata.get("refer_required")),
        _bool_suggestion(metadata.get("ai_suggested_refer")),
        _bool_suggestion(metadata.get("gma_suggested_refer")),
        _gma_patient_level_suggestion(metadata.get("gma_patient_level_result")),
        _ocr_text_suggestion(_nested(metadata, "ocr", "dr_report", "dr_data", "result"), disease="dr"),
        _ocr_text_suggestion(_nested(metadata, "ocr", "amd_report", "amd_data", "result"), disease="amd"),
        _ocr_text_suggestion(_nested(metadata, "ocr", "glaucoma_report", "glaucoma_data", "result"), disease="glaucoma"),
    ]
    if REFERRAL_SUGGESTION_YES in values:
        return REFERRAL_SUGGESTION_YES
    if REFERRAL_SUGGESTION_NO in values:
        return REFERRAL_SUGGESTION_NO
    return REFERRAL_SUGGESTION_MISSING


def _bool_suggestion(value: Any) -> str:
    if value is True:
        return REFERRAL_SUGGESTION_YES
    if value is False:
        return REFERRAL_SUGGESTION_NO
    return REFERRAL_SUGGESTION_MISSING


def _gma_patient_level_suggestion(value: Any) -> str:
    text = _clean_text(value)
    if not text:
        return REFERRAL_SUGGESTION_MISSING
    compact = text.replace(" ", "_").replace("-", "_")
    if compact in {"no_refer", "non_refer", "non_referrable", "non_referable"}:
        return REFERRAL_SUGGESTION_NO
    if "refer" in compact:
        return REFERRAL_SUGGESTION_YES
    return REFERRAL_SUGGESTION_MISSING


def _ocr_text_suggestion(value: Any, *, disease: str) -> str:
    text = _clean_text(value)
    if not text:
        return REFERRAL_SUGGESTION_MISSING

    if disease == "dr":
        if text.startswith("no signs of dr or amd detected"):
            return REFERRAL_SUGGESTION_NO
        if text.startswith("no signs of dr detected"):
            return REFERRAL_SUGGESTION_NO
        if text.startswith("signs of dr or amd detected"):
            return REFERRAL_SUGGESTION_YES
        if text.startswith("signs of dr detected"):
            return REFERRAL_SUGGESTION_YES
        return REFERRAL_SUGGESTION_MISSING

    if disease == "amd":
        if text.startswith("no signs of dr or amd detected"):
            return REFERRAL_SUGGESTION_NO
        if text.startswith("no signs of amd detected"):
            return REFERRAL_SUGGESTION_NO
        if text.startswith("signs of dr or amd detected"):
            return REFERRAL_SUGGESTION_YES
        if text.startswith("signs of amd detected"):
            return REFERRAL_SUGGESTION_YES
        return REFERRAL_SUGGESTION_MISSING

    if disease == "glaucoma":
        if "no referable glaucoma" in text:
            return REFERRAL_SUGGESTION_NO
        if "referral suggested" in text or "refer immediately" in text:
            return REFERRAL_SUGGESTION_YES
        if "referable glaucoma" in text or "referable glacuoma" in text:
            return REFERRAL_SUGGESTION_YES

    return REFERRAL_SUGGESTION_MISSING


def _nested(value: dict[str, Any], *path: str) -> Any:
    current: Any = value
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().lower().split())
