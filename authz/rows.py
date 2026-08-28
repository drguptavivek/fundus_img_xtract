"""SQL predicates matching the named single-resource scope helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from sqlalchemy import and_, exists, false, or_, select, true
from sqlalchemy.sql.elements import ColumnElement

from authz.context import AccessContext
from authz.scopes import _hospital_ids_for_roles, _roles


@dataclass(frozen=True)
class RecordColumns:
    """Columns that describe a row's authorization lineage.

    ``classical_only`` must be explicit when the model cannot contain project
    data.  A missing ``project_id`` column otherwise means incomplete lineage
    and therefore denies classical row access.
    """

    project_id: Any | None = None
    hospital_id: Any | None = None
    lab_unit_id: Any | None = None
    user_id: Any | None = None
    classical_only: bool = False


def self_rows(context: AccessContext, columns: RecordColumns) -> ColumnElement:
    if not context.active or columns.user_id is None:
        return false()
    return columns.user_id == context.user_id


def assigned_lab_rows(
    context: AccessContext,
    roles: Iterable[str],
    columns: RecordColumns,
) -> ColumnElement:
    if (
        not context.has_any_global_role(_roles(roles))
        or columns.lab_unit_id is None
        or (columns.project_id is None and not columns.classical_only)
    ):
        return false()
    lab_clause = columns.lab_unit_id.in_(context.assigned_lab_unit_ids or {-1})
    return (
        lab_clause
        if columns.classical_only
        else and_(columns.project_id.is_(None), lab_clause)
    )


def hospital_rows(
    context: AccessContext,
    roles: Iterable[str],
    columns: RecordColumns,
) -> ColumnElement:
    if columns.hospital_id is None and columns.lab_unit_id is None:
        return false()
    if columns.project_id is None and not columns.classical_only:
        return false()
    hospital_ids = _hospital_ids_for_roles(context, _roles(roles))
    if not hospital_ids:
        return false()
    if columns.hospital_id is not None:
        hospital_clause = columns.hospital_id.in_(hospital_ids)
    else:
        from models import LabUnit

        hospital_clause = exists(
            select(LabUnit.id).where(
                LabUnit.id == columns.lab_unit_id,
                LabUnit.hospital_id.in_(hospital_ids),
            )
        )
    return (
        hospital_clause
        if columns.classical_only
        else and_(columns.project_id.is_(None), hospital_clause)
    )


def project_rows(
    context: AccessContext,
    roles: Iterable[str],
    columns: RecordColumns,
    *,
    project_wide: bool = False,
) -> ColumnElement:
    if not context.active or columns.project_id is None:
        return false()

    from data_authorization.models import ProjectRoleGrant
    from models import Role
    from project_configuration.models import ProjectLabUnit

    role_names = _roles(roles)
    configured_clause = true()
    conditions = [
        ProjectRoleGrant.user_id == context.user_id,
        ProjectRoleGrant.project_id == columns.project_id,
        ProjectRoleGrant.active.is_(True),
        Role.name.in_(role_names),
    ]
    if columns.lab_unit_id is not None:
        # Project data is visible only through an active configured
        # Project-Lab Unit, including for project-wide grants. This mirrors
        # the single-record project scope check.
        configured_clause = exists(
            select(ProjectLabUnit.id).where(
                ProjectLabUnit.project_id == columns.project_id,
                ProjectLabUnit.lab_unit_id == columns.lab_unit_id,
                ProjectLabUnit.active.is_(True),
            )
        )
    if project_wide:
        conditions.extend(
            [
                ProjectRoleGrant.scope_type == "project",
                ProjectRoleGrant.lab_unit_id.is_(None),
            ]
        )
    elif columns.lab_unit_id is None:
        conditions.append(ProjectRoleGrant.scope_type == "project")
    else:
        conditions.append(
            or_(
                ProjectRoleGrant.scope_type == "project",
                and_(
                    ProjectRoleGrant.scope_type == "lab_unit",
                    ProjectRoleGrant.lab_unit_id == columns.lab_unit_id,
                ),
            )
        )
    return and_(
        columns.project_id.is_not(None),
        configured_clause,
        exists(
            select(ProjectRoleGrant.id)
            .join(Role, Role.id == ProjectRoleGrant.role_id)
            .where(*conditions)
        ),
    )


def admin_rows(context: AccessContext) -> ColumnElement:
    return true() if context.has_any_global_role(frozenset({"admin"})) else false()


def where_any(query, *predicates: ColumnElement):
    return query.where(or_(*predicates) if predicates else false())


def where_all(query, *predicates: ColumnElement):
    return query.where(and_(*predicates) if predicates else false())


def role_scoped_rows(
    query,
    context: AccessContext,
    columns: RecordColumns,
    *,
    lab_roles: Iterable[str] = (),
    hospital_roles: Iterable[str] = (),
    project_roles: Iterable[str] = (),
    allow_admin: bool = False,
    project_wide: bool = False,
    owner_roles: Iterable[str] = (),
):
    """Apply explicit alternative role-scope paths to a row query.

    The route supplies the roles for each branch.  No action name, model
    registry, or hidden policy lookup is involved.
    """
    predicates: list[ColumnElement] = []
    if allow_admin:
        predicates.append(admin_rows(context))
    lab = _roles(lab_roles)
    if lab:
        predicates.append(assigned_lab_rows(context, lab, columns))
    hospital = _roles(hospital_roles)
    if hospital:
        predicates.append(hospital_rows(context, hospital, columns))
    project = _roles(project_roles)
    if project:
        predicates.append(
            project_rows(context, project, columns, project_wide=project_wide)
        )
    owners = _roles(owner_roles)
    if owners and context.has_any_global_role(owners):
        predicates.append(self_rows(context, columns))
    return where_any(query, *predicates)


def lab_unit_choice_rows(
    query,
    context: AccessContext,
    *,
    lab_roles: Iterable[str] = (),
    hospital_roles: Iterable[str] = (),
    project_roles: Iterable[str] = (),
    allow_admin: bool = False,
):
    """Scope a LabUnit picker through explicit classical/project roles."""
    from data_authorization.models import ProjectRoleGrant
    from models import LabUnit, Role
    from project_configuration.models import ProjectLabUnit

    predicates: list[ColumnElement] = []
    if allow_admin and context.has_any_global_role(frozenset({"admin"})):
        predicates.append(true())
    lab = _roles(lab_roles)
    if context.has_any_global_role(lab):
        predicates.append(LabUnit.id.in_(context.assigned_lab_unit_ids or {-1}))
    hospital_ids = _hospital_ids_for_roles(context, _roles(hospital_roles))
    if hospital_ids:
        predicates.append(LabUnit.hospital_id.in_(hospital_ids))
    project = _roles(project_roles)
    if project:
        predicates.append(
            exists(
                select(ProjectRoleGrant.id)
                .join(Role, Role.id == ProjectRoleGrant.role_id)
                .join(
                    ProjectLabUnit,
                    and_(
                        ProjectLabUnit.project_id == ProjectRoleGrant.project_id,
                        ProjectLabUnit.lab_unit_id == LabUnit.id,
                        ProjectLabUnit.active.is_(True),
                    ),
                )
                .where(
                    ProjectRoleGrant.user_id == context.user_id,
                    ProjectRoleGrant.active.is_(True),
                    Role.name.in_(project),
                    or_(
                        ProjectRoleGrant.scope_type == "project",
                        and_(
                            ProjectRoleGrant.scope_type == "lab_unit",
                            ProjectRoleGrant.lab_unit_id == LabUnit.id,
                        ),
                    ),
                )
            )
        )
    return where_any(query, *predicates)


def hospital_choice_rows(
    query,
    context: AccessContext,
    *,
    lab_roles: Iterable[str] = (),
    hospital_roles: Iterable[str] = (),
    project_roles: Iterable[str] = (),
    allow_admin: bool = False,
):
    """Scope a Hospital picker through explicit classical/project roles."""
    from data_authorization.models import ProjectRoleGrant
    from models import Hospital, LabUnit, Role
    from project_configuration.models import ProjectLabUnit

    predicates: list[ColumnElement] = []
    if allow_admin and context.has_any_global_role(frozenset({"admin"})):
        predicates.append(true())
    lab = _roles(lab_roles)
    if context.has_any_global_role(lab):
        if context.assigned_lab_unit_ids:
            predicates.append(
                exists(
                    select(LabUnit.id).where(
                        LabUnit.hospital_id == Hospital.id,
                        LabUnit.id.in_(context.assigned_lab_unit_ids),
                    )
                )
            )
    hospital_ids = _hospital_ids_for_roles(context, _roles(hospital_roles))
    if hospital_ids:
        predicates.append(Hospital.id.in_(hospital_ids))
    project = _roles(project_roles)
    if project:
        predicates.append(
            exists(
                select(ProjectRoleGrant.id)
                .join(Role, Role.id == ProjectRoleGrant.role_id)
                .join(
                    ProjectLabUnit,
                    and_(
                        ProjectLabUnit.project_id == ProjectRoleGrant.project_id,
                        ProjectLabUnit.active.is_(True),
                    ),
                )
                .join(
                    LabUnit,
                    and_(
                        LabUnit.id == ProjectLabUnit.lab_unit_id,
                        LabUnit.hospital_id == Hospital.id,
                    ),
                )
                .where(
                    ProjectRoleGrant.user_id == context.user_id,
                    ProjectRoleGrant.active.is_(True),
                    Role.name.in_(project),
                    or_(
                        ProjectRoleGrant.scope_type == "project",
                        and_(
                            ProjectRoleGrant.scope_type == "lab_unit",
                            ProjectRoleGrant.lab_unit_id == ProjectLabUnit.lab_unit_id,
                        ),
                    ),
                )
            )
        )
    return where_any(query, *predicates)
