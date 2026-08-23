"""Resolve every persisted relationship an actor holds, in one pass.

This is the single place that turns application tables into
``RelationshipGrant`` values. Both renderers consume its output: the pure
engine (``authz.engine.authorize``) for per-object decisions, and the
predicate compiler (``authz.predicates``) for list filtering. Because they
share one grant set, a per-object decision and a list filter can never
disagree about what the actor is allowed to see.

Grants are resolved independently of any resource. A project role grant is
emitted once per persisted ``ProjectRoleGrant`` row carrying its own scope
(``project``, ``hospital`` or ``lab_unit``); the engine's
``_matches_project_scope`` then decides whether a given resource falls
inside that scope. This keeps the resolver to a fixed number of queries
regardless of how many resources are later authorized against it.

Resource-bound grants (``TASK_ELIGIBILITY``, ``MEDIA_UPLOADER``,
``SIGNED_MEDIA_TOKEN``) are deliberately not resolved here: they only make
sense once a specific resource is known, and ``media.authorization`` already
derives them per request.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from flask import g, has_request_context
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from authz.adapters import (
    actor_from_user,
    admin_global_grant,
    grading_slot_grants,
    hospital_scope_grant,
    lab_unit_assignment_grants,
    own_hospital_grant,
    self_grant,
)
from authz.types import AuthzActor, GrantSource, RelationshipGrant


@dataclass(frozen=True)
class ResolvedGrants:
    """An actor together with every relationship grant resolved for them."""

    actor: AuthzActor
    grants: tuple[RelationshipGrant, ...] = field(default_factory=tuple)
    project_lab_ids: dict[int, frozenset[int]] = field(default_factory=dict)
    """Active lab units configured on each project the actor has a grant for."""

    def of(self, source: GrantSource) -> tuple[RelationshipGrant, ...]:
        """Return only the grants from one relationship source."""
        return tuple(grant for grant in self.grants if grant.source == source)

    @property
    def project_ids(self) -> frozenset[int]:
        """Every project the actor holds any explicit relationship with."""
        return frozenset(
            int(grant.attr("project_id"))
            for grant in self.grants
            if grant.source in _PROJECT_SOURCES and grant.attr("project_id") is not None
        )


_PROJECT_SOURCES = frozenset({
    GrantSource.PROJECT_ROLE,
    GrantSource.LEGACY_PROJECT_CAPABILITY,
    GrantSource.PROJECT_COLLABORATOR,
})

_REQUEST_CACHE_ATTR = "_authz_resolved_grants"


def resolve_grants(db: Session, user) -> ResolvedGrants:
    """Resolve all of one user's grants, memoised per request.

    Within a Flask request the result is cached on ``g`` keyed by user id, so
    a route that authorizes several actions pays for resolution once.
    ``authz.cache`` bumps its epochs when authorization tables change, but a
    request is short enough that a stale read within it is acceptable.
    """
    user_id = int(getattr(user, "id"))
    if has_request_context():
        cached = getattr(g, _REQUEST_CACHE_ATTR, None)
        if cached is not None and cached[0] == user_id:
            return cached[1]

    resolved = _resolve_uncached(db, user)

    if has_request_context():
        setattr(g, _REQUEST_CACHE_ATTR, (user_id, resolved))
    return resolved


def _resolve_uncached(db: Session, user) -> ResolvedGrants:
    actor = actor_from_user(user)
    grants: list[RelationshipGrant] = [self_grant(actor.id)]

    for grant in (admin_global_grant(actor), hospital_scope_grant(actor), own_hospital_grant(actor)):
        if grant is not None:
            grants.append(grant)
    grants.extend(lab_unit_assignment_grants(user))

    project_grants, project_lab_ids = _project_role_grants(db, actor.id)
    grants.extend(project_grants)
    grants.extend(_legacy_capability_grants(db, actor.id))
    grants.extend(_legacy_collaborator_grants(db, actor.id))
    grants.extend(_upload_assignment_grants(db, actor.id))
    grants.extend(_grading_slot_grants(db, actor.id))

    return ResolvedGrants(
        actor=actor, grants=tuple(grants), project_lab_ids=project_lab_ids
    )


def _project_role_grants(db: Session, user_id: int) -> tuple[list[RelationshipGrant], dict[int, frozenset[int]]]:
    """One grant per active ProjectRoleGrant row, carrying its own scope.

    Rows whose lab unit is no longer configured on the project are dropped,
    mirroring the project-boundary check in
    ``data_authorization.service.project_role_names_for_scope``.
    """
    from data_authorization.models import ProjectRoleGrant
    from models import LabUnit
    from project_configuration.models import ProjectLabUnit

    rows = db.execute(
        select(ProjectRoleGrant)
        .options(selectinload(ProjectRoleGrant.role))
        .where(ProjectRoleGrant.user_id == user_id, ProjectRoleGrant.active.is_(True))
    ).scalars().all()
    if not rows:
        return [], {}

    project_ids = {row.project_id for row in rows}
    configured = db.execute(
        select(ProjectLabUnit.project_id, ProjectLabUnit.lab_unit_id, LabUnit.hospital_id)
        .join(LabUnit, LabUnit.id == ProjectLabUnit.lab_unit_id)
        .where(ProjectLabUnit.project_id.in_(project_ids), ProjectLabUnit.active.is_(True))
    ).all()
    labs_by_project: dict[int, set[int]] = {}
    hospitals_by_project: dict[int, set[int]] = {}
    for project_id, lab_unit_id, hospital_id in configured:
        labs_by_project.setdefault(project_id, set()).add(lab_unit_id)
        hospitals_by_project.setdefault(project_id, set()).add(hospital_id)

    # Merge rows that share (project, scope) so one grant carries all role
    # names for that scope, matching what the engine expects in role_names.
    merged: dict[tuple[int, int | None, int | None], set[str]] = {}
    for row in rows:
        if row.lab_unit_id is not None and row.lab_unit_id not in labs_by_project.get(row.project_id, ()):
            continue
        if row.hospital_id is not None and row.hospital_id not in hospitals_by_project.get(row.project_id, ()):
            continue
        key = (row.project_id, row.hospital_id, row.lab_unit_id)
        merged.setdefault(key, set()).add(row.role.name)

    configured_by_project = {
        project_id: frozenset(lab_ids) for project_id, lab_ids in labs_by_project.items()
    }
    return [
        RelationshipGrant(
            source=GrantSource.PROJECT_ROLE,
            hospital_id=hospital_id,
            lab_unit_id=lab_unit_id,
            attributes={
                "project_id": project_id,
                "hospital_id": hospital_id,
                "lab_unit_id": lab_unit_id,
                "role_names": frozenset(role_names),
            },
        )
        for (project_id, hospital_id, lab_unit_id), role_names in merged.items()
    ], configured_by_project


def _legacy_capability_grants(db: Session, user_id: int) -> list[RelationshipGrant]:
    """One grant per active legacy ProjectEncounterSetPermission row."""
    from encounter_sets.models import ProjectEncounterSetPermission
    from encounter_sets.permissions import CAPABILITY_COLUMNS
    from models import LabUnit

    rows = db.execute(
        select(ProjectEncounterSetPermission, LabUnit.hospital_id)
        .join(LabUnit, LabUnit.id == ProjectEncounterSetPermission.lab_unit_id)
        .where(
            ProjectEncounterSetPermission.user_id == user_id,
            ProjectEncounterSetPermission.active.is_(True),
        )
    ).all()
    grants: list[RelationshipGrant] = []
    for row, hospital_id in rows:
        capabilities = frozenset(
            name for name, column in CAPABILITY_COLUMNS.items() if getattr(row, column.key)
        )
        if not capabilities:
            continue
        grants.append(RelationshipGrant(
            source=GrantSource.LEGACY_PROJECT_CAPABILITY,
            hospital_id=hospital_id,
            lab_unit_id=row.lab_unit_id,
            attributes={
                "project_id": row.project_id,
                "hospital_id": hospital_id,
                "lab_unit_id": row.lab_unit_id,
                "capabilities": capabilities,
            },
        ))
    return grants


def _legacy_collaborator_grants(db: Session, user_id: int) -> list[RelationshipGrant]:
    """Project-wide collaborator grants from the legacy project membership table."""
    from encounter_sets.permissions import legacy_collaborator_project_ids

    return [
        RelationshipGrant(
            source=GrantSource.PROJECT_COLLABORATOR,
            attributes={"project_id": project_id, "hospital_id": None, "lab_unit_id": None},
        )
        for project_id in legacy_collaborator_project_ids(db, user_id=user_id)
    ]


def _upload_assignment_grants(db: Session, user_id: int) -> list[RelationshipGrant]:
    """One grant per active project upload assignment.

    An uploader's reach in a project is the (project, lab unit) pairs their
    upload profile assignments cover. This is what lets them see the uploads
    they made and the progress of those jobs, and it carries no verification
    or grading authority.
    """
    from upload_profiles.models import ProjectUploadProfile, ProjectUploadProfileAssignment

    rows = db.execute(
        select(ProjectUploadProfile.project_id, ProjectUploadProfileAssignment.lab_unit_id)
        .join(
            ProjectUploadProfileAssignment,
            ProjectUploadProfileAssignment.project_upload_profile_id == ProjectUploadProfile.id,
        )
        .where(
            ProjectUploadProfileAssignment.user_id == user_id,
            ProjectUploadProfileAssignment.active.is_(True),
            ProjectUploadProfile.active.is_(True),
        )
    ).all()
    return [
        RelationshipGrant(
            source=GrantSource.UPLOAD_PROFILE,
            lab_unit_id=lab_unit_id,
            attributes={"project_id": project_id, "lab_unit_id": lab_unit_id, "hospital_id": None},
        )
        for project_id, lab_unit_id in {(p, l) for p, l in rows}
    ]

def _grading_slot_grants(db: Session, user_id: int) -> list[RelationshipGrant]:
    from models import UserDiseaseUnitRole

    slots = db.execute(
        select(UserDiseaseUnitRole).where(
            UserDiseaseUnitRole.user_id == user_id,
            UserDiseaseUnitRole.active.is_(True),
        )
    ).scalars().all()
    return grading_slot_grants(slots)
