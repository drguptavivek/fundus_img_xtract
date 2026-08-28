"""Resource access and clinical-result disclosure for the shared viewer."""

from __future__ import annotations

from sqlalchemy.orm import Session

from authz import (
    AuthorizationDenied,
    access_context,
    admin_scope,
    assigned_lab_scope,
    hospital_scope,
    project_scope,
    require_any,
)
from models import PatientEncounters
from services.uploads.access import encounter_record_scope


VERIFY_ROLE_NAMES = frozenset({
    "verifier",
    "admin",
    "local_admin",
    "data_manager",
    "fileUploader",
})

ACCESS_ROLE_NAMES = frozenset({
    "local_admin",
    "data_manager",
    "fileUploader",
    "ophthalmologist",
    "optometrist",
    "verifier",
})

PROJECT_ACCESS_ROLE_NAMES = frozenset({
    "project_pi",
    "site_pi",
    "project_admin",
    "collaborator",
    "verifier",
    "field_optometrist",
    "field_ophthalmologist",
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
    context = access_context(db, user)
    try:
        record = encounter_record_scope(context, encounter)
        require_any(
            admin_scope(context),
            assigned_lab_scope(context, ACCESS_ROLE_NAMES, record),
            hospital_scope(context, ACCESS_ROLE_NAMES, record),
            project_scope(context, PROJECT_ACCESS_ROLE_NAMES, record),
        )
        return True
    except AuthorizationDenied:
        return False


def can_view_results(db: Session, *, user, encounter: PatientEncounters | None, project_id: int | None,
                     hospital_id: int | None, lab_unit_id: int | None) -> bool:
    if encounter is None:
        return False
    context = access_context(db, user)
    try:
        record = encounter_record_scope(context, encounter)
        require_any(
            admin_scope(context),
            assigned_lab_scope(context, RESULT_ROLE_NAMES, record),
            hospital_scope(context, RESULT_ROLE_NAMES, record),
            project_scope(context, RESULT_ROLE_NAMES, record),
        )
        return True
    except AuthorizationDenied:
        return False


def can_verify_encounter(db: Session, *, user, encounter: PatientEncounters) -> bool:
    """Whether this user may verify one EncounterSet encounter.

    Verification needs a verification role in both branches. Outside a
    project the role is paired with classical lab scope; inside one it must
    come through an explicit project role grant. The legacy project
    capability row no longer confers verification: no active row grants it,
    and those rows are being retired.
    """
    if not encounter.is_set_based:
        return False
    context = access_context(db, user)
    try:
        record = encounter_record_scope(context, encounter)
        require_any(
            admin_scope(context),
            assigned_lab_scope(context, VERIFY_ROLE_NAMES, record),
            hospital_scope(context, VERIFY_ROLE_NAMES, record),
            project_scope(context, VERIFY_ROLE_NAMES, record),
        )
        return True
    except AuthorizationDenied:
        return False
