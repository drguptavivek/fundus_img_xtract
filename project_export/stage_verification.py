"""verification stage: what verifiers recorded per encounter and per image."""
from __future__ import annotations

from sqlalchemy import select

from models import DirectImageVerify, User
from project_sync.inventory import (
    KIND_DIRECT_IMAGE,
    KIND_ENCOUNTER_FILE,
    KIND_ENCOUNTER_SET_IMAGE,
    _first_non_empty,
    _sanitize_metadata_dict,
)
from verify_encounter_set.models import EncounterVerificationHistory

from . import stage_api
from .tables import BuildContext, _chunks, _json, ts

LATERALITY_KEYS = ("laterality", "eye", "eye_side")
CENTERING_KEYS = ("focus", "fundus_image_view", "fundus_field", "field", "image_segment", "centering")
GAZE_KEYS = ("gaze_position", "strabismus_gaze_position", "gaze")

_SIDES = {"R": "R", "RIGHT": "R", "OD": "R", "RE": "R", "L": "L", "LEFT": "L", "OS": "L", "LE": "L",
          "OU": "B", "BOTH": "B"}


def side(value) -> str | None:
    """Normalise laterality spellings (RIGHT / OD / R ...) to R, L, B; unknown -> None."""
    return _SIDES.get(str(value).strip().upper()) if value not in (None, "") else None


def _dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def _encounter_rows(ctx: BuildContext) -> list[dict]:
    rows = []
    for encounter in ctx.encounters:
        block = _dict(_dict(encounter.metadata_json).get("verification"))
        rows.append({
            "encounter_uuid": encounter.uuid,
            "status": encounter.encounter_verified_status,
            "verified_by": encounter.encounter_verified_by,
            "verified_at": encounter.encounter_verified_at,
            "dr_verified_status": encounter.dr_verified_status,
            "dr_verified_by": encounter.dr_verified_by,
            "dr_verified_at": encounter.dr_verified_at,
            "glaucoma_verified_status": encounter.glaucoma_verified_status,
            "glaucoma_verified_by": encounter.glaucoma_verified_by,
            "glaucoma_verified_at": encounter.glaucoma_verified_at,
            "excluded": encounter.encounter_verified_status == "excluded",  # current state; history is in `verification`
            "excluded_reason": block.get("excluded_reason"),
            "excluded_by": block.get("excluded_by"),
            "excluded_at": ts(block.get("excluded_at")),
            "observation": block.get("observation"),
            "observation_by": block.get("observation_by"),
            "observation_at": ts(block.get("observation_at")),
            "referral_suggestion": encounter.referral_suggestion,
            "referral_suggestion_updated_at": encounter.referral_suggestion_updated_at,
            "verification": _json(block or None),
        })
    return rows


def _direct_verifications(ctx: BuildContext) -> dict:
    """Latest verification per exported direct upload id."""
    latest = {}
    for chunk in _chunks([row.id for row in ctx.direct_uploads]):
        for row in ctx.db.execute(
            select(DirectImageVerify).where(DirectImageVerify.image_upload_id.in_(chunk)).order_by(DirectImageVerify.id)
        ).scalars():
            latest[row.image_upload_id] = row
    return latest


def _image_rows(ctx: BuildContext) -> list[dict]:
    source = stage_api.source_images(ctx)
    direct = _direct_verifications(ctx)
    rows = []
    for encounter_id, items in ctx.media.items():
        encounter_uuid = ctx.encounter_uuid[encounter_id]
        for kind, image in items:
            meta = _dict(getattr(image, "metadata_json", None))
            block = _dict(meta.get("verification"))
            if kind == KIND_ENCOUNTER_FILE:
                laterality, centering, gaze = image.eye_side, image.centering, None
            else:
                laterality = _first_non_empty(meta, *LATERALITY_KEYS)
                centering = _first_non_empty(meta, *CENTERING_KEYS)
                gaze = _first_non_empty(meta, *GAZE_KEYS)
            api = source.get(image.uuid)
            effective, original = side(laterality), side(api.laterality if api else None)
            rows.append({
                "image_uuid": image.uuid,
                "encounter_uuid": encounter_uuid,
                "kind": kind,
                "laterality": laterality,
                "centering": centering,
                "gaze_position": gaze,
                "source_laterality": api.laterality if api else None,
                "source_field": api.field if api else None,
                "laterality_corrected": (effective != original) if effective and original else None,
                "is_reviewed": getattr(image, "is_reviewed", None),
                "is_not_gradable": getattr(image, "is_not_gradable", None),
                "not_gradable_reason": getattr(image, "not_gradable_reason", None),
                "visible_to_grader": getattr(image, "visible_to_grader", None),
                "creates_task": getattr(image, "creates_task", None),
                "referral_needed_or_positive": getattr(image, "referral_needed_or_positive_image", None),
                "referral_updated_at": getattr(image, "referral_needed_or_positive_image_updated_at", None),
                "observation": block.get("observation"),
                "observation_by": block.get("observation_by"),
                "direct_verification_status": None,
                "direct_verification_remarks": None,
                "direct_verified_by_user_id": None,
                "direct_verified_at": None,
            })
    for row in ctx.direct_uploads:
        verification = direct.get(row.id)
        rows.append({
            "image_uuid": row.uuid, "encounter_uuid": None, "kind": KIND_DIRECT_IMAGE,
            "laterality": None, "centering": None, "gaze_position": None,
            "source_laterality": None, "source_field": None, "laterality_corrected": None,
            "is_reviewed": None, "is_not_gradable": None, "not_gradable_reason": None,
            "visible_to_grader": None, "creates_task": None,
            "referral_needed_or_positive": None, "referral_updated_at": None,
            "observation": None, "observation_by": None,
            "direct_verification_status": verification.verified_status if verification else None,
            "direct_verification_remarks": verification.remarks if verification else None,
            "direct_verified_by_user_id": verification.verified_by_id if verification else None,
            "direct_verified_at": verification.verified_at if verification else None,
        })
    return rows


def _history_rows(ctx: BuildContext) -> list[dict]:
    usernames = dict(ctx.db.execute(select(User.id, User.username)).all())
    rows = []
    for chunk in _chunks(list(ctx.encounter_by_id)):
        for item in ctx.db.execute(
            select(EncounterVerificationHistory)
            .where(EncounterVerificationHistory.patient_encounter_id.in_(chunk))
            .order_by(EncounterVerificationHistory.id)
        ).scalars():
            pii = ctx.allows_pii(item.patient_encounter_id)
            rows.append({
                "encounter_uuid": ctx.encounter_uuid[item.patient_encounter_id],
                "action_type": item.action_type,
                "actor_username": usernames.get(item.actor_user_id),
                "occurred_at": item.occurred_at,
                "note": item.note,
                "before": _json(_sanitize_metadata_dict(item.before_json, pii=pii)),
                "after": _json(_sanitize_metadata_dict(item.after_json, pii=pii)),
            })
    return rows


def build(ctx: BuildContext) -> dict[str, list[dict]]:
    return {
        "verification_encounters": _encounter_rows(ctx),
        "verification_images": _image_rows(ctx),
        "verification_history": _history_rows(ctx),
    }
