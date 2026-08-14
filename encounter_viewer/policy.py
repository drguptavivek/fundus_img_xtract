"""Resource access and clinical-result disclosure for the shared viewer."""

from __future__ import annotations

from sqlalchemy.orm import Session

from data_authorization.service import project_role_names_for_scope
from encounter_sets.permissions import (
    CAPABILITY_ANALYTICS_VIEW,
    CAPABILITY_DATASET_CREATION,
    CAPABILITY_DATA_EXPORT,
    CAPABILITY_DISCREPANCY_REVIEW,
    CAPABILITY_REGRADE_ADJUDICATION,
    CAPABILITY_VERIFY,
    apply_project_permission_scope,
    is_project_permission_admin,
    legacy_project_capabilities_for_scope,
    user_is_legacy_project_collaborator,
)
from models import PatientEncounters
from utils.hospital_scoping import apply_scoping


RESULT_CAPABILITIES = frozenset({
    CAPABILITY_ANALYTICS_VIEW,
    CAPABILITY_DISCREPANCY_REVIEW,
    CAPABILITY_DATA_EXPORT,
    CAPABILITY_DATASET_CREATION,
    CAPABILITY_REGRADE_ADJUDICATION,
})
RESULT_ROLE_NAMES = frozenset({
    "admin",
    "local_admin",
    "data_manager",
    "analytics_viewer",
    "discrepancy_reviewer",
    "data_exporter",
    "dataset_creator",
    "regrade_adjudicator",
})


def can_access_encounter(db: Session, *, user, encounter: PatientEncounters) -> bool:
    if encounter.project_id is None:
        query = db.query(PatientEncounters.id).filter(PatientEncounters.id == encounter.id)
        # Clinical-result authorization is decided separately below.  This is
        # only the classical hospital/lab media scope, so it must not invoke
        # the analytics capability filter used for project EncounterSets.
        return apply_scoping(query, PatientEncounters, user, "viewer").first() is not None
    if is_project_permission_admin(user):
        return True
    hospital_id = encounter.lab_unit.hospital_id if encounter.lab_unit else None
    roles = project_role_names_for_scope(
        db,
        user_id=user.id,
        project_id=encounter.project_id,
        hospital_id=hospital_id,
        lab_unit_id=encounter.lab_unit_id,
    )
    capabilities = legacy_project_capabilities_for_scope(
        db,
        user_id=user.id,
        project_id=encounter.project_id,
        lab_unit_id=encounter.lab_unit_id,
    ) if encounter.lab_unit_id else frozenset()
    return bool(
        roles
        or capabilities
        or user_is_legacy_project_collaborator(
            db, user_id=user.id, project_id=encounter.project_id
        )
    )


def can_view_results(db: Session, *, user, encounter: PatientEncounters | None, project_id: int | None,
                     hospital_id: int | None, lab_unit_id: int | None) -> bool:
    if is_project_permission_admin(user):
        return True
    if project_id is None:
        if not user.has_role(*RESULT_ROLE_NAMES):
            return False
        if encounter is None:
            return True
        query = db.query(PatientEncounters.id).filter(PatientEncounters.id == encounter.id)
        return apply_scoping(query, PatientEncounters, user, "viewer").first() is not None
    roles = project_role_names_for_scope(
        db,
        user_id=user.id,
        project_id=project_id,
        hospital_id=hospital_id,
        lab_unit_id=lab_unit_id,
    )
    if roles & RESULT_ROLE_NAMES:
        return True
    capabilities = legacy_project_capabilities_for_scope(
        db,
        user_id=user.id,
        project_id=project_id,
        lab_unit_id=lab_unit_id,
    ) if lab_unit_id else frozenset()
    return bool(capabilities & RESULT_CAPABILITIES)


def can_verify_encounter(db: Session, *, user, encounter: PatientEncounters) -> bool:
    if not encounter.is_set_based:
        return False
    if encounter.project_id is None:
        if not user.has_role("admin", "local_admin", "data_manager", "fileUploader", "optometrist"):
            return False
        query = db.query(PatientEncounters.id).filter(PatientEncounters.id == encounter.id)
        return apply_scoping(query, PatientEncounters, user, "upload").first() is not None
    query = db.query(PatientEncounters.id).filter(PatientEncounters.id == encounter.id)
    return apply_project_permission_scope(
        query, PatientEncounters, user, CAPABILITY_VERIFY
    ).first() is not None
