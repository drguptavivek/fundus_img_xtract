"""Persisted project-role grant management and scope resolution.

This deep module owns the database representation and containment rules for
project, hospital, and lab-unit role grants. It supplies normalized role
relationships to the pure :mod:`authz` policy engine; it is not a second policy
decision engine and it does not serve media or handle HTTP requests.
"""
from __future__ import annotations

from collections.abc import Iterable
import logging

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.orm import Session, aliased, selectinload

from models import Hospital, LabUnit, Project, Role, User
from utils.log_sanitize import sanitize_log_value

from .dto import ProjectRoleGrantDTO, ProjectRoleGrantInput
from .exceptions import ProjectGrantPermissionDenied, ProjectGrantValidationError
from .models import (
    HOSPITAL_SCOPE,
    LAB_UNIT_SCOPE,
    PROJECT_SCOPE,
    PROJECT_SCOPE_TYPES,
    ProjectRoleGrant,
)


from .policy import (
    PROJECT_ADMIN_ASSIGNABLE_ROLE_NAMES,
    PROJECT_ASSIGNABLE_ROLE_NAMES,
    ROLE_PROJECT_ADMIN,
)
from project_configuration.service import configured_project_lab_unit_ids
from project_configuration.models import ProjectLabUnit


PROJECT_GRANT_MANAGER_ROLES = frozenset({ROLE_PROJECT_ADMIN})

_LOGGER = logging.getLogger("project_authorization")


def _invalidate_field_cache(project_id: int | None) -> None:
    """Drop cached field reads whenever a project grant changes.

    Field responses are cached per user and stamped with a fingerprint of the
    caller's grants, but the stamp only changes once the new grants are read.
    Bumping here means a revoked grant stops serving cached patient data on the
    very next request instead of when the entry happens to expire.
    """
    if project_id is None:
        return
    try:
        from app_cache import init_cache
        from field_workbench.cache import bump_project

        init_cache()
        bump_project(project_id)
    except Exception:  # noqa: BLE001 - cache state must not fail a grant change
        _LOGGER.warning("Field cache invalidation failed after project grant change")


def upsert_project_role_grant(
    db: Session,
    *,
    actor: User,
    data: ProjectRoleGrantInput,
) -> ProjectRoleGrantDTO:
    """Create/update a role-scope grant; the first active grant is membership."""
    project, target_user, role = _validate_grant_input(db, data)
    _require_manage_scope(db, actor=actor, data=data)

    statement = select(ProjectRoleGrant).where(
        ProjectRoleGrant.project_id == project.id,
        ProjectRoleGrant.user_id == target_user.id,
        ProjectRoleGrant.role_id == role.id,
        ProjectRoleGrant.scope_type == data.scope_type,
    )
    if data.scope_type == PROJECT_SCOPE:
        statement = statement.where(
            ProjectRoleGrant.hospital_id.is_(None),
            ProjectRoleGrant.lab_unit_id.is_(None),
        )
    elif data.scope_type == HOSPITAL_SCOPE:
        statement = statement.where(ProjectRoleGrant.hospital_id == data.hospital_id)
    else:
        statement = statement.where(ProjectRoleGrant.lab_unit_id == data.lab_unit_id)

    row = db.execute(statement).scalar_one_or_none()
    if row is None:
        row = ProjectRoleGrant(
            project_id=project.id,
            user_id=target_user.id,
            role=role,
            scope_type=data.scope_type,
            hospital_id=data.hospital_id,
            lab_unit_id=data.lab_unit_id,
            active=data.active,
        )
        db.add(row)
        change = "created"
    else:
        change = "activated" if data.active and not row.active else "deactivated" if not data.active and row.active else "updated"
        row.active = data.active
    db.flush()
    _log_grant_edit(actor=actor, row=row, change=change)
    db.refresh(row, attribute_names=["project", "user", "role", "hospital", "lab_unit"])
    _invalidate_field_cache(row.project_id)
    return grant_to_dto(row)


def replace_project_role_grants(
    db: Session,
    *,
    actor: User,
    project_id: int,
    user_id: int,
    role_names: Iterable[str],
    scope_type: str,
    hospital_id: int | None = None,
    lab_unit_id: int | None = None,
    original_scope_type: str | None = None,
    original_hospital_id: int | None = None,
    original_lab_unit_id: int | None = None,
) -> tuple[ProjectRoleGrantDTO, ...]:
    """Replace all roles at one exact user/project scope without deleting history."""
    selected_roles = {
        role_name.strip()
        for role_name in role_names
        if role_name and role_name.strip()
    }
    actor_assignable_roles = _actor_assignable_role_names(actor)
    unsupported = selected_roles - actor_assignable_roles
    if unsupported:
        raise ProjectGrantValidationError("One or more roles cannot be assigned within a project.")
    scope_input = ProjectRoleGrantInput(
        project_id=project_id,
        user_id=user_id,
        role_name=next(iter(selected_roles), "collaborator"),
        scope_type=scope_type,
        hospital_id=hospital_id,
        lab_unit_id=lab_unit_id,
    )
    _validate_scope_target(db, scope_input)
    _require_manage_scope(db, actor=actor, data=scope_input)

    original_scope = (
        original_scope_type,
        original_hospital_id,
        original_lab_unit_id,
    )
    requested_scope = (scope_type, hospital_id, lab_unit_id)
    if original_scope_type and original_scope != requested_scope:
        original_input = ProjectRoleGrantInput(
            project_id=project_id,
            user_id=user_id,
            role_name=scope_input.role_name,
            scope_type=original_scope_type,
            hospital_id=original_hospital_id,
            lab_unit_id=original_lab_unit_id,
        )
        _validate_scope_target(db, original_input)
        _require_manage_scope(db, actor=actor, data=original_input)
        old_rows = db.execute(
            select(ProjectRoleGrant)
            .join(Role, Role.id == ProjectRoleGrant.role_id)
            .where(
                ProjectRoleGrant.project_id == project_id,
                ProjectRoleGrant.user_id == user_id,
                Role.name.in_(actor_assignable_roles),
                _exact_scope_clause(
                    scope_type=original_scope_type,
                    hospital_id=original_hospital_id,
                    lab_unit_id=original_lab_unit_id,
                ),
            )
            .options(selectinload(ProjectRoleGrant.role))
        ).scalars().all()
        for row in old_rows:
            if row.active:
                row.active = False
                _log_grant_edit(actor=actor, row=row, change="scope_removed")

    exact_scope = _exact_scope_clause(
        scope_type=scope_type,
        hospital_id=hospital_id,
        lab_unit_id=lab_unit_id,
    )
    existing = db.execute(
        select(ProjectRoleGrant)
        .join(Role, Role.id == ProjectRoleGrant.role_id)
        .where(
            ProjectRoleGrant.project_id == project_id,
            ProjectRoleGrant.user_id == user_id,
            exact_scope,
            Role.name.in_(actor_assignable_roles),
        )
        .options(
            selectinload(ProjectRoleGrant.user),
            selectinload(ProjectRoleGrant.role),
            selectinload(ProjectRoleGrant.hospital),
            selectinload(ProjectRoleGrant.lab_unit).selectinload(LabUnit.hospital),
        )
    ).scalars().all()
    existing_by_role = {row.role.name: row for row in existing}
    for role_name, row in existing_by_role.items():
        should_be_active = role_name in selected_roles
        if row.active != should_be_active:
            row.active = should_be_active
            _log_grant_edit(
                actor=actor,
                row=row,
                change="activated" if should_be_active else "removed",
            )
    for role_name in selected_roles - set(existing_by_role):
        upsert_project_role_grant(
            db,
            actor=actor,
            data=ProjectRoleGrantInput(
                project_id=project_id,
                user_id=user_id,
                role_name=role_name,
                scope_type=scope_type,
                hospital_id=hospital_id,
                lab_unit_id=lab_unit_id,
            ),
        )
    db.flush()
    _invalidate_field_cache(project_id)
    return tuple(
        grant_to_dto(row)
        for row in db.execute(
            select(ProjectRoleGrant)
            .where(
                ProjectRoleGrant.project_id == project_id,
                ProjectRoleGrant.user_id == user_id,
                ProjectRoleGrant.active.is_(True),
                exact_scope,
            )
            .options(
                selectinload(ProjectRoleGrant.user),
                selectinload(ProjectRoleGrant.role),
                selectinload(ProjectRoleGrant.hospital),
                selectinload(ProjectRoleGrant.lab_unit).selectinload(LabUnit.hospital),
            )
            .order_by(ProjectRoleGrant.role_id)
        ).scalars().all()
    )


def deactivate_project_role_grant(
    db: Session,
    *,
    actor: User,
    project_id: int,
    grant_id: int,
) -> ProjectRoleGrantDTO:
    """Deactivate one exact grant after checking the actor can manage its scope."""
    row = db.execute(
        select(ProjectRoleGrant)
        .where(
            ProjectRoleGrant.id == grant_id,
            ProjectRoleGrant.project_id == project_id,
        )
        .options(
            selectinload(ProjectRoleGrant.user),
            selectinload(ProjectRoleGrant.role),
            selectinload(ProjectRoleGrant.hospital),
            selectinload(ProjectRoleGrant.lab_unit).selectinload(LabUnit.hospital),
        )
    ).scalar_one_or_none()
    if row is None:
        raise ProjectGrantValidationError("Project role grant not found.")
    scope_input = ProjectRoleGrantInput(
        project_id=row.project_id,
        user_id=row.user_id,
        role_name=row.role.name,
        scope_type=row.scope_type,
        hospital_id=row.hospital_id,
        lab_unit_id=row.lab_unit_id,
        active=False,
    )
    _require_manage_scope(db, actor=actor, data=scope_input)
    if row.active:
        row.active = False
        _log_grant_edit(actor=actor, row=row, change="removed")
        db.flush()
    _invalidate_field_cache(row.project_id)
    return grant_to_dto(row)


def list_project_role_grants(
    db: Session,
    *,
    actor: User,
    project_id: int,
) -> tuple[ProjectRoleGrantDTO, ...]:
    """List grants the actor is allowed to manage in one project."""
    project = db.get(Project, project_id)
    if project is None:
        raise ProjectGrantValidationError("Project not found.")

    statement = (
        select(ProjectRoleGrant)
        .join(Role, Role.id == ProjectRoleGrant.role_id)
        .options(
            selectinload(ProjectRoleGrant.user),
            selectinload(ProjectRoleGrant.role),
            selectinload(ProjectRoleGrant.hospital),
            selectinload(ProjectRoleGrant.lab_unit).selectinload(LabUnit.hospital),
        )
        .where(
            ProjectRoleGrant.project_id == project_id,
            Role.name.in_(PROJECT_ASSIGNABLE_ROLE_NAMES),
        )
        .order_by(
            ProjectRoleGrant.active.desc(),
            ProjectRoleGrant.user_id,
            ProjectRoleGrant.role_id,
            ProjectRoleGrant.scope_type,
        )
    )
    visible_clause = _manageable_grant_clause(db, actor=actor, project_id=project_id)
    if visible_clause is None:
        raise ProjectGrantPermissionDenied("You cannot manage role grants for this project.")
    if visible_clause is not True:
        statement = statement.where(visible_clause)
    return tuple(grant_to_dto(row) for row in db.execute(statement).scalars().all())


def grant_to_dto(row: ProjectRoleGrant) -> ProjectRoleGrantDTO:
    """Detach one ORM grant for API/template consumption."""
    return ProjectRoleGrantDTO(
        id=row.id,
        project_id=row.project_id,
        user_id=row.user_id,
        username=row.user.username,
        user_name=row.user.full_name or row.user.username,
        role_name=row.role.name,
        scope_type=row.scope_type,
        hospital_id=row.hospital_id,
        hospital_name=(
            row.hospital.name
            if row.hospital
            else row.lab_unit.hospital.name if row.lab_unit and row.lab_unit.hospital else None
        ),
        lab_unit_id=row.lab_unit_id,
        lab_unit_name=row.lab_unit.name if row.lab_unit else None,
        active=row.active,
    )


def user_has_project_role(
    db: Session,
    *,
    user_id: int,
    project_id: int,
    role_names: Iterable[str],
    hospital_id: int | None = None,
    lab_unit_id: int | None = None,
) -> bool:
    """Return whether a project role grant contains the requested resource scope."""
    roles = {name.strip() for name in role_names if name and name.strip()}
    if not roles:
        return False
    clause = project_role_grant_exists_clause(
        user_id=user_id,
        project_id=project_id,
        role_names=roles,
        hospital_id=hospital_id,
        lab_unit_id=lab_unit_id,
    )
    return bool(db.execute(select(clause)).scalar_one())


def user_has_any_project_role(
    db: Session,
    *,
    user_id: int,
    role_names: Iterable[str],
) -> bool:
    """Return whether the user has any active project grant for a role."""
    roles = tuple({name.strip() for name in role_names if name and name.strip()})
    if not roles:
        return False
    return db.execute(
        select(ProjectRoleGrant.id)
        .join(Role, Role.id == ProjectRoleGrant.role_id)
        .where(
            ProjectRoleGrant.user_id == user_id,
            ProjectRoleGrant.active.is_(True),
            Role.name.in_(roles),
        )
        .limit(1)
    ).scalar_one_or_none() is not None


def project_role_names_for_scope(
    db: Session,
    *,
    user_id: int,
    project_id: int,
    hospital_id: int | None = None,
    lab_unit_id: int | None = None,
) -> frozenset[str]:
    """Resolve active role names whose project scope contains one resource."""
    if lab_unit_id is not None and not db.execute(
        select(ProjectLabUnit.id).where(
            ProjectLabUnit.project_id == project_id,
            ProjectLabUnit.lab_unit_id == lab_unit_id,
            ProjectLabUnit.active.is_(True),
        )
    ).scalar_one_or_none():
        return frozenset()
    if hospital_id is not None and not db.execute(
        select(ProjectLabUnit.id)
        .join(LabUnit, LabUnit.id == ProjectLabUnit.lab_unit_id)
        .where(
            ProjectLabUnit.project_id == project_id,
            ProjectLabUnit.active.is_(True),
            LabUnit.hospital_id == hospital_id,
        )
        .limit(1)
    ).scalar_one_or_none():
        return frozenset()
    scope_conditions = [ProjectRoleGrant.scope_type == PROJECT_SCOPE]
    if hospital_id is not None:
        scope_conditions.append(and_(
            ProjectRoleGrant.scope_type == HOSPITAL_SCOPE,
            ProjectRoleGrant.hospital_id == hospital_id,
        ))
    if lab_unit_id is not None:
        scope_conditions.append(and_(
            ProjectRoleGrant.scope_type == LAB_UNIT_SCOPE,
            ProjectRoleGrant.lab_unit_id == lab_unit_id,
        ))
        if hospital_id is None:
            lab = aliased(LabUnit)
            scope_conditions.append(and_(
                ProjectRoleGrant.scope_type == HOSPITAL_SCOPE,
                exists().where(
                    lab.id == lab_unit_id,
                    lab.hospital_id == ProjectRoleGrant.hospital_id,
                ),
            ))
    return frozenset(db.execute(
        select(Role.name)
        .join(ProjectRoleGrant, ProjectRoleGrant.role_id == Role.id)
        .where(
            ProjectRoleGrant.user_id == user_id,
            ProjectRoleGrant.project_id == project_id,
            ProjectRoleGrant.active.is_(True),
            or_(*scope_conditions),
        )
    ).scalars())


def project_role_grant_exists_clause(
    *,
    user_id: int,
    project_id,
    role_names: Iterable[str],
    hospital_id=None,
    lab_unit_id=None,
):
    """Build a correlated EXISTS clause for a project resource lineage."""
    roles = tuple({name.strip() for name in role_names if name and name.strip()})
    grant = aliased(ProjectRoleGrant)
    role = aliased(Role)
    lab = aliased(LabUnit)
    scope_conditions = [grant.scope_type == PROJECT_SCOPE]
    if hospital_id is not None:
        scope_conditions.append(
            and_(grant.scope_type == HOSPITAL_SCOPE, grant.hospital_id == hospital_id)
        )
    if lab_unit_id is not None:
        scope_conditions.append(
            and_(grant.scope_type == LAB_UNIT_SCOPE, grant.lab_unit_id == lab_unit_id)
        )
        if hospital_id is None:
            scope_conditions.append(
                and_(
                    grant.scope_type == HOSPITAL_SCOPE,
                    exists().where(lab.id == lab_unit_id, lab.hospital_id == grant.hospital_id),
                )
            )
    conditions = [
        grant.project_id == project_id,
        grant.user_id == user_id,
        grant.active.is_(True),
        grant.role_id == role.id,
        role.name.in_(roles),
        or_(*scope_conditions),
    ]
    if lab_unit_id is not None:
        conditions.append(exists().where(
            ProjectLabUnit.project_id == project_id,
            ProjectLabUnit.lab_unit_id == lab_unit_id,
            ProjectLabUnit.active.is_(True),
        ))
    elif hospital_id is not None:
        configured_lab = aliased(LabUnit)
        conditions.append(exists().where(
            ProjectLabUnit.project_id == project_id,
            ProjectLabUnit.lab_unit_id == configured_lab.id,
            configured_lab.hospital_id == hospital_id,
            ProjectLabUnit.active.is_(True),
        ))
    return exists().where(*conditions)


def _validate_grant_input(
    db: Session, data: ProjectRoleGrantInput
) -> tuple[Project, User, Role]:
    _validate_scope_target(db, data)
    project = db.get(Project, data.project_id)
    if project is None or not project.active:
        raise ProjectGrantValidationError("An active project is required.")
    target_user = db.get(User, data.user_id)
    if target_user is None or not target_user.is_active:
        raise ProjectGrantValidationError("An active user is required.")
    role = db.execute(select(Role).where(Role.name == data.role_name)).scalar_one_or_none()
    if role is None or role.name not in PROJECT_ASSIGNABLE_ROLE_NAMES:
        raise ProjectGrantValidationError("Select an assignable project role.")

    return project, target_user, role


def _validate_scope_target(db: Session, data: ProjectRoleGrantInput) -> None:
    if data.scope_type not in PROJECT_SCOPE_TYPES:
        raise ProjectGrantValidationError("scope_type must be project, hospital, or lab_unit.")
    if db.get(Project, data.project_id) is None or db.get(User, data.user_id) is None:
        raise ProjectGrantValidationError("Project and user are required.")
    if data.scope_type == PROJECT_SCOPE:
        if data.hospital_id is not None or data.lab_unit_id is not None:
            raise ProjectGrantValidationError("Project scope cannot include a hospital or lab unit.")
    elif data.scope_type == HOSPITAL_SCOPE:
        if data.hospital_id is None or data.lab_unit_id is not None:
            raise ProjectGrantValidationError("Hospital scope requires exactly one hospital.")
        if db.get(Hospital, data.hospital_id) is None:
            raise ProjectGrantValidationError("Hospital not found.")
        configured_hospital_ids = set(db.execute(
            select(LabUnit.hospital_id).where(
                LabUnit.id.in_(configured_project_lab_unit_ids(db, project_id=data.project_id) or {-1})
            )
        ).scalars())
        if data.hospital_id not in configured_hospital_ids:
            raise ProjectGrantValidationError("Hospital has no Lab Unit configured for this project.")
    else:
        if data.lab_unit_id is None or data.hospital_id is not None:
            raise ProjectGrantValidationError("Lab-unit scope requires exactly one lab unit.")
        if db.get(LabUnit, data.lab_unit_id) is None:
            raise ProjectGrantValidationError("Lab unit not found.")
        if data.lab_unit_id not in configured_project_lab_unit_ids(db, project_id=data.project_id):
            raise ProjectGrantValidationError("Lab unit is not configured for this project.")


def _exact_scope_clause(*, scope_type: str, hospital_id: int | None, lab_unit_id: int | None):
    if scope_type == PROJECT_SCOPE:
        return and_(
            ProjectRoleGrant.scope_type == PROJECT_SCOPE,
            ProjectRoleGrant.hospital_id.is_(None),
            ProjectRoleGrant.lab_unit_id.is_(None),
        )
    if scope_type == HOSPITAL_SCOPE:
        return and_(
            ProjectRoleGrant.scope_type == HOSPITAL_SCOPE,
            ProjectRoleGrant.hospital_id == hospital_id,
        )
    return and_(
        ProjectRoleGrant.scope_type == LAB_UNIT_SCOPE,
        ProjectRoleGrant.lab_unit_id == lab_unit_id,
    )


def _log_grant_edit(*, actor: User, row: ProjectRoleGrant, change: str) -> None:
    _LOGGER.info(
        "project_role_grant change=%s actor_user_id=%s project_id=%s target_user_id=%s "
        "role=%s scope_type=%s hospital_id=%s lab_unit_id=%s active=%s",
        sanitize_log_value(change),
        actor.id,
        row.project_id,
        row.user_id,
        sanitize_log_value(row.role.name if row.role else row.role_id),
        sanitize_log_value(row.scope_type),
        row.hospital_id,
        row.lab_unit_id,
        row.active,
    )


def _require_manage_scope(db: Session, *, actor: User, data: ProjectRoleGrantInput) -> None:
    if actor.has_role("admin"):
        return
    if data.role_name not in PROJECT_ADMIN_ASSIGNABLE_ROLE_NAMES:
        raise ProjectGrantPermissionDenied("Only a System Admin can assign project governance roles.")
    if db.execute(
        select(ProjectRoleGrant.id)
        .join(Role, Role.id == ProjectRoleGrant.role_id)
        .where(
            ProjectRoleGrant.project_id == data.project_id,
            ProjectRoleGrant.user_id == actor.id,
            ProjectRoleGrant.active.is_(True),
            Role.name.in_(PROJECT_GRANT_MANAGER_ROLES),
        )
        .limit(1)
    ).scalar_one_or_none() is not None:
        return
    raise ProjectGrantPermissionDenied("You cannot manage the requested project scope.")


def _manageable_grant_clause(db: Session, *, actor: User, project_id: int):
    if actor.has_role("admin"):
        return True
    conditions = []
    manager_grants = db.execute(
        select(ProjectRoleGrant)
        .join(Role, Role.id == ProjectRoleGrant.role_id)
        .where(
            ProjectRoleGrant.project_id == project_id,
            ProjectRoleGrant.user_id == actor.id,
            ProjectRoleGrant.active.is_(True),
            Role.name.in_(PROJECT_GRANT_MANAGER_ROLES),
        )
    ).scalars().all()
    if manager_grants:
        configured_lab_ids = configured_project_lab_unit_ids(db, project_id=project_id)
        configured_hospital_ids = select(LabUnit.hospital_id).where(
            LabUnit.id.in_(configured_lab_ids or {-1})
        )
        conditions.extend([
            ProjectRoleGrant.scope_type == PROJECT_SCOPE,
            and_(
                ProjectRoleGrant.scope_type == HOSPITAL_SCOPE,
                ProjectRoleGrant.hospital_id.in_(configured_hospital_ids),
            ),
            and_(
                ProjectRoleGrant.scope_type == LAB_UNIT_SCOPE,
                ProjectRoleGrant.lab_unit_id.in_(configured_lab_ids or {-1}),
            ),
        ])
    return or_(*conditions) if conditions else None


def _actor_assignable_role_names(actor: User) -> frozenset[str]:
    """System Admin appoints governance; Project Admin delegates operations."""
    if actor.has_role("admin"):
        return PROJECT_ASSIGNABLE_ROLE_NAMES
    return PROJECT_ADMIN_ASSIGNABLE_ROLE_NAMES
