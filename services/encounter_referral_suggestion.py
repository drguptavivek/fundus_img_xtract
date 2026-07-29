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
    if (
        preserve_existing_when_missing
        and suggestion == REFERRAL_SUGGESTION_MISSING
        and encounter.referral_suggestion in {REFERRAL_SUGGESTION_YES, REFERRAL_SUGGESTION_NO}
    ):
        return encounter.referral_suggestion
    encounter.referral_suggestion = suggestion
    encounter.referral_suggestion_updated_at = utcnow()
    db.add(encounter)
    db.flush()
    return suggestion


def _metadata_referral_suggestion(metadata: dict[str, Any]) -> str:
    values = [
        _bool_suggestion(metadata.get("refer_required")),
        _bool_suggestion(metadata.get("ai_suggested_refer")),
        _bool_suggestion(metadata.get("gma_suggested_refer")),
        _gma_patient_level_suggestion(metadata.get("gma_patient_level_result")),
        _ocr_text_suggestion(_nested(metadata, "ocr", "dr_report", "dr_data", "result"), disease="dr"),
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
        if text.startswith("no signs of dr detected"):
            return REFERRAL_SUGGESTION_NO
        if text.startswith("signs of dr detected"):
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
