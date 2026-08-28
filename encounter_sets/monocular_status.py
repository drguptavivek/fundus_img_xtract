"""Scoped post-verification correction of canonical monocular status."""
from __future__ import annotations

from dataclasses import dataclass
import logging

from db_transaction_manager import transaction_scope
from encounter_sets.permissions import (
    apply_classical_or_project_permission_scope,
)
from models import PatientEncounters


audit_logger = logging.getLogger("security.audit")
VERIFY_ROLES = frozenset(
    {
        "verifier",
        "local_admin",
        "data_manager",
        "fileUploader",
        "optometrist",
        "field_optometrist",
        "field_ophthalmologist",
    }
)


@dataclass(frozen=True)
class MonocularStatusResult:
    success: bool
    message: str
    status_code: int
    encounter_uuid: str | None = None
    is_monocular: bool | None = None


def update_monocular_status(*, encounter_uuid: str, is_monocular: bool, user) -> MonocularStatusResult:
    """Update the canonical patient flag without reopening verification."""
    with transaction_scope() as db:
        query = db.query(PatientEncounters).filter(
            PatientEncounters.uuid == encounter_uuid,
            PatientEncounters.is_set_based.is_(True),
        )
        query = apply_classical_or_project_permission_scope(
            query,
            PatientEncounters,
            user,
            VERIFY_ROLES,
            classical_operation="upload",
        )
        encounter = query.first()
        if encounter is None:
            return MonocularStatusResult(False, "EncounterSet not found.", 404)

        metadata = dict(encounter.metadata_json or {})
        patient = dict(metadata.get("patient") or {})
        previous = patient.get("is_monocular") is True
        patient["is_monocular"] = is_monocular
        metadata["patient"] = patient
        encounter.metadata_json = metadata
        db.flush()

        audit_logger.info(
            "EncounterSet monocular status corrected",
            extra={
                "user_id": user.id,
                "encounter_uuid": encounter.uuid,
                "previous_is_monocular": previous,
                "is_monocular": is_monocular,
                "encounter_verified_status": encounter.encounter_verified_status,
            },
        )
        return MonocularStatusResult(
            True,
            "Monocular status updated.",
            200,
            encounter_uuid=encounter.uuid,
            is_monocular=is_monocular,
        )
