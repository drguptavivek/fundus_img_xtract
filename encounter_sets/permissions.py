"""Lean role/scope helpers retained for EncounterSet workflow callers.

The old per-user capability table is deliberately not consulted.  Project
authority comes from one ProjectRoleGrant at project or exact Project-Lab Unit
scope; classical authority comes from current roles plus Lab Unit/hospital
relationships.
"""

from __future__ import annotations

from sqlalchemy import and_, exists, false, or_, select, true
from sqlalchemy.orm import aliased

from authz import RecordColumns, access_context, role_scoped_rows
from authz.behaviors import role_lab_units
from data_authorization.service import project_role_grant_exists_clause
from models import GradingTask, LabUnit, User
from tasks.access import task_columns


HOSPITAL_WIDE_ROLES = frozenset({"local_admin", "data_manager"})


def _columns(model_class) -> RecordColumns:
    if model_class is GradingTask:
        return task_columns(model_class)
    return RecordColumns(
        project_id=getattr(model_class, "project_id", None),
        hospital_id=getattr(model_class, "hospital_id", None),
        lab_unit_id=getattr(model_class, "lab_unit_id", None),
    )


def _session(query):
    db = getattr(query, "session", None)
    if db is None:
        raise TypeError("EncounterSet scoping requires an ORM Query with a session.")
    return db


def apply_project_permission_scope(query, model_class, user: User, roles):
    return role_scoped_rows(
        query,
        access_context(_session(query), user),
        _columns(model_class),
        project_roles=frozenset(roles),
        allow_admin=True,
    )


def apply_classical_or_project_permission_scope(
    query,
    model_class,
    user: User,
    roles,
    *,
    classical_operation: str | None = None,
):
    del classical_operation
    roles = frozenset(roles)
    return role_scoped_rows(
        query,
        access_context(_session(query), user),
        _columns(model_class),
        lab_roles=roles,
        hospital_roles=roles & HOSPITAL_WIDE_ROLES,
        project_roles=roles,
        allow_admin=True,
    )


def user_has_task_capability(db, *, user: User, task_id: int, roles) -> bool:
    roles = frozenset(roles)
    query = role_scoped_rows(
        db.query(GradingTask.id).filter(GradingTask.id == task_id),
        access_context(db, user),
        task_columns(GradingTask),
        lab_roles=roles,
        hospital_roles=roles & HOSPITAL_WIDE_ROLES,
        project_roles=roles,
        allow_admin=True,
    )
    return query.first() is not None


def project_task_capability_clause(task_id_column, user: User, roles):
    """Correlated task clause matching the same explicit role/scope paths."""
    if user.has_role("admin"):
        return true()
    roles = frozenset(roles)
    task = aliased(GradingTask)
    assigned_ids = {
        int(lab.id) for lab in (getattr(user, "lab_units", None) or ())
        if getattr(lab, "id", None) is not None
    }
    classical = and_(
        task.project_id.is_(None),
        task.lab_unit_id.in_(assigned_ids or {-1}),
    ) if user.has_role(*roles) else false()
    project = project_role_grant_exists_clause(
        user_id=user.id,
        project_id=task.project_id,
        role_names=roles,
        lab_unit_id=task.lab_unit_id,
    )
    return exists(
        select(task.id).where(
            task.id == task_id_column,
            or_(classical, project),
        )
    )


def capability_lab_unit_ids(db, *, user: User, roles) -> set[int]:
    roles = frozenset(roles)
    query = role_lab_units(
        db,
        select(LabUnit.id),
        user,
        lab_roles=roles,
        hospital_roles=roles & HOSPITAL_WIDE_ROLES,
        project_roles=roles,
        allow_admin=True,
    )
    return set(db.execute(query).scalars())


def apply_task_capability_scope(query, task_entity, user: User, roles):
    roles = frozenset(roles)
    return role_scoped_rows(
        query,
        access_context(_session(query), user),
        task_columns(task_entity),
        lab_roles=roles,
        hospital_roles=roles & HOSPITAL_WIDE_ROLES,
        project_roles=roles,
        allow_admin=True,
    )
