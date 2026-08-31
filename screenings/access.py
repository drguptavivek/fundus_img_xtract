"""Authorization boundaries for the legacy classical screenings surface."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from flask import abort
from sqlalchemy import false, select

from authz.behaviors import role_lab_units
from models import LabUnit, PatientEncounters, User


SCREENING_LAB_ROLES = frozenset({"fileUploader", "optometrist"})
SCREENING_HOSPITAL_ROLES = frozenset({"data_manager"})


class ScreeningNotAuthorized(Exception):
    """Raised when a persisted screening exists outside the actor's scope."""


def authorized_screening_lab_unit_ids(db: Any, user: User) -> frozenset[int]:
    """Resolve classical screening scope, including manager hospital reach."""
    query = role_lab_units(
        db,
        select(LabUnit.id),
        user,
        lab_roles=SCREENING_LAB_ROLES,
        hospital_roles=SCREENING_HOSPITAL_ROLES,
        allow_admin=False,
    )
    return frozenset(db.execute(query).scalars().all())


def screening_is_authorized(
    encounter: PatientEncounters,
    *,
    is_admin: bool,
    allowed_lab_unit_ids: Iterable[int] | None,
) -> bool:
    """Return whether an actor may use a legacy screening encounter.

    Legacy screening routes are classical-only.  A global admin is the sole
    break-glass exception; every other actor needs a concrete classical
    encounter and an exact assigned Lab Unit.  In particular, a project row
    never becomes visible merely because its Lab Unit is assigned.
    """
    if is_admin:
        return True

    lab_unit_ids = frozenset(allowed_lab_unit_ids or ())
    return (
        encounter.project_id is None
        and encounter.lab_unit_id is not None
        and encounter.lab_unit_id in lab_unit_ids
    )


def apply_screening_scope(
    query: Any,
    *,
    is_admin: bool,
    allowed_lab_unit_ids: Iterable[int] | None,
) -> Any:
    """Apply the persisted-record scope used by every screening query.

    The empty set deliberately produces no rows.  ``project_id IS NULL`` and
    non-NULL Lab Unit checks are kept in SQL so counts, lists, and navigation
    cannot diverge from object-level authorization.
    """
    if is_admin:
        return query

    lab_unit_ids = frozenset(allowed_lab_unit_ids or ())
    if not lab_unit_ids:
        return query.filter(false())

    return query.filter(
        PatientEncounters.project_id.is_(None),
        PatientEncounters.lab_unit_id.is_not(None),
        PatientEncounters.lab_unit_id.in_(lab_unit_ids),
    )


def load_screening(
    db: Any,
    encounter_id: int,
    *,
    is_admin: bool,
    allowed_lab_unit_ids: Iterable[int] | None,
    options: tuple[Any, ...] = (),
) -> PatientEncounters | None:
    """Load one encounter and enforce the same boundary as list queries.

    The query addresses exactly one persisted record.  Missing rows return
    ``None``; an existing but out-of-scope row raises a distinct exception so
    callers can preserve their existing 403 behavior without broad loading.
    """
    query = db.query(PatientEncounters).options(*options).filter(
        PatientEncounters.id == encounter_id
    )
    encounter = query.first()
    if encounter is not None and not screening_is_authorized(
        encounter,
        is_admin=is_admin,
        allowed_lab_unit_ids=allowed_lab_unit_ids,
    ):
        raise ScreeningNotAuthorized
    return encounter


def load_screening_or_abort(
    db: Any,
    encounter_id: int,
    *,
    is_admin: bool,
    allowed_lab_unit_ids: Iterable[int] | None,
    options: tuple[Any, ...] = (),
) -> PatientEncounters:
    """Load an authorized encounter, preserving 404/403 route semantics."""
    try:
        encounter = load_screening(
            db,
            encounter_id,
            is_admin=is_admin,
            allowed_lab_unit_ids=allowed_lab_unit_ids,
            options=options,
        )
    except ScreeningNotAuthorized:
        abort(403)
    if encounter is None:
        abort(404, description="Encounter not found")
    return encounter
