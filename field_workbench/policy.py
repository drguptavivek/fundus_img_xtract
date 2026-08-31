"""Authorization for the field surface.

Scope is always re-derived from the database. JWT claims carry role and lab-unit
hints for the client's benefit, but they are never trusted for authorization:
a token minted before a grant was revoked would otherwise keep working until it
expired.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import and_, exists, literal, or_, select

from auth.roles import FIELD_ROLE_NAMES
from data_authorization.models import (
    LAB_UNIT_SCOPE,
    PROJECT_SCOPE,
    ProjectRoleGrant,
)
from models import LabUnit, PatientEncounters, Project, Role
from project_configuration.models import ProjectLabUnit

from .exceptions import FieldNotFound

# Roles that may read the field surface for a project. Field roles are the point
# of this module; the operational roles are included so existing staff are not
# locked out of a screen their web access already covers.
FIELD_READ_ROLES = frozenset(
    set(FIELD_ROLE_NAMES) | {"admin", "local_admin", "data_manager", "optometrist"}
)


@dataclass(frozen=True)
class FieldScope:
    """The caller's resolved reach inside one project."""

    project_id: int
    project_wide: bool
    hospital_ids: frozenset[int]
    lab_unit_ids: frozenset[int]
    role_names: frozenset[str]

    @property
    def is_field_staff(self) -> bool:
        return bool(self.role_names & set(FIELD_ROLE_NAMES))


def resolve_project_scope(db, *, user, project_id: int) -> tuple[Project, FieldScope]:
    """Return the project and the caller's scope, or raise :class:`FieldNotFound`.

    An unauthorized project raises not-found rather than forbidden so callers
    cannot probe which project ids exist.
    """
    project = db.get(Project, project_id)
    if project is None or not project.active:
        raise FieldNotFound("Project not found.")

    if user.has_role("admin"):
        return project, FieldScope(
            project_id=project_id,
            project_wide=True,
            hospital_ids=frozenset(),
            lab_unit_ids=frozenset(),
            role_names=frozenset({"admin"}),
        )

    grants = db.execute(
        select(ProjectRoleGrant, Role.name)
        .join(Role, Role.id == ProjectRoleGrant.role_id)
        .where(
            ProjectRoleGrant.project_id == project_id,
            ProjectRoleGrant.user_id == user.id,
            ProjectRoleGrant.active.is_(True),
            Role.name.in_(FIELD_READ_ROLES),
            or_(
                ProjectRoleGrant.scope_type == PROJECT_SCOPE,
                and_(
                    ProjectRoleGrant.scope_type == LAB_UNIT_SCOPE,
                    ProjectRoleGrant.lab_unit_id.in_(
                        select(ProjectLabUnit.lab_unit_id).where(
                            ProjectLabUnit.project_id == project_id,
                            ProjectLabUnit.active.is_(True),
                        )
                    ),
                ),
            ),
        )
    ).all()
    if not grants:
        raise FieldNotFound("Project not found.")

    role_names = frozenset(name for _, name in grants)
    project_wide = any(grant.scope_type == PROJECT_SCOPE for grant, _ in grants)
    return project, FieldScope(
        project_id=project_id,
        project_wide=project_wide,
        hospital_ids=frozenset(),
        lab_unit_ids=frozenset(
            grant.lab_unit_id for grant, _ in grants
            if grant.scope_type == LAB_UNIT_SCOPE and grant.lab_unit_id is not None
        ),
        role_names=role_names,
    )


def encounter_scope_clause(scope: FieldScope):
    """SQL restricting encounters to the caller's reach within the project."""
    if scope.project_wide:
        return exists(
            select(ProjectLabUnit.id).where(
                ProjectLabUnit.project_id == scope.project_id,
                ProjectLabUnit.lab_unit_id == PatientEncounters.lab_unit_id,
                ProjectLabUnit.active.is_(True),
            )
        )
    return (
        PatientEncounters.lab_unit_id.in_(scope.lab_unit_ids)
        if scope.lab_unit_ids
        else literal(False)
    )


def list_field_projects(db, *, user) -> list[tuple[Project, FieldScope]]:
    """Every project this caller may read through the field surface."""
    if user.has_role("admin"):
        projects = db.execute(
            select(Project).where(Project.active.is_(True)).order_by(Project.title)
        ).scalars().all()
        return [
            (
                project,
                FieldScope(
                    project_id=project.id,
                    project_wide=True,
                    hospital_ids=frozenset(),
                    lab_unit_ids=frozenset(),
                    role_names=frozenset({"admin"}),
                ),
            )
            for project in projects
        ]

    project_ids = db.execute(
        select(ProjectRoleGrant.project_id)
        .join(Role, Role.id == ProjectRoleGrant.role_id)
        .where(
            ProjectRoleGrant.user_id == user.id,
            ProjectRoleGrant.active.is_(True),
            Role.name.in_(FIELD_READ_ROLES),
        )
        .distinct()
    ).scalars().all()

    out = []
    for project_id in project_ids:
        try:
            out.append(resolve_project_scope(db, user=user, project_id=project_id))
        except FieldNotFound:
            continue
    return sorted(out, key=lambda item: item[0].title or "")


def can_trigger_fetch(scope: FieldScope) -> bool:
    return bool(scope.role_names & FIELD_READ_ROLES)


def can_request_inference(scope: FieldScope) -> bool:
    return bool(scope.role_names & FIELD_READ_ROLES)
