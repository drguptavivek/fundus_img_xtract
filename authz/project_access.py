"""Small named checks for project-level surfaces.

Exact data rows are still scoped with ``project_scope`` / ``project_rows``.
These checks answer only whether a project page or operation may be entered;
the mutation service enforces target containment again.
"""

from __future__ import annotations

from dataclasses import dataclass

from authz.context import access_context
from authz.project_roles import (
    PROJECT_ADMIN,
    PROJECT_ASSIGNABLE_ROLES,
    PROJECT_PI,
    SITE_PI,
)
from authz.scopes import RecordScope, admin_scope, project_scope
from upload_profiles.access import has_remidio_sync_assignment, has_upload_assignment


def _allowed(
    db,
    user,
    *,
    project_id: int,
    roles,
    lab_unit_id: int | None = None,
    allow_admin: bool = True,
) -> bool:
    if not getattr(user, "is_authenticated", True):
        return False
    context = access_context(db, user)
    if allow_admin and admin_scope(context).allowed:
        return True
    return project_scope(
        context,
        roles,
        RecordScope.project(project_id=project_id, lab_unit_id=lab_unit_id),
    ).allowed


def can_view_project(db, user, *, project_id: int, lab_unit_id: int | None = None) -> bool:
    return _allowed(
        db,
        user,
        project_id=project_id,
        lab_unit_id=lab_unit_id,
        roles=PROJECT_ASSIGNABLE_ROLES,
    )


def can_browse_project(db, user, *, project_id: int, lab_unit_id: int | None = None) -> bool:
    return _allowed(
        db,
        user,
        project_id=project_id,
        lab_unit_id=lab_unit_id,
        roles=PROJECT_ASSIGNABLE_ROLES,
    )


def can_browse_project_pii(db, user, *, project_id: int, lab_unit_id: int | None = None) -> bool:
    return _allowed(
        db,
        user,
        project_id=project_id,
        lab_unit_id=lab_unit_id,
        roles=PROJECT_ASSIGNABLE_ROLES - {"collaborator"},
    )


def can_manage_project_access(db, user, *, project_id: int, lab_unit_id: int | None = None) -> bool:
    return _allowed(
        db,
        user,
        project_id=project_id,
        lab_unit_id=lab_unit_id,
        roles={PROJECT_PI, SITE_PI, PROJECT_ADMIN},
    )


def can_manage_project_uploaders(db, user, *, project_id: int, lab_unit_id: int | None = None) -> bool:
    return _allowed(
        db,
        user,
        project_id=project_id,
        lab_unit_id=lab_unit_id,
        roles={PROJECT_ADMIN},
    )


def can_run_wai(db, user, *, project_id: int, lab_unit_id: int | None = None) -> bool:
    return _allowed(
        db,
        user,
        project_id=project_id,
        lab_unit_id=lab_unit_id,
        roles={"verifier", "optometrist", "field_optometrist", "field_ophthalmologist"},
    )


def can_view_wai_results(db, user, *, project_id: int, lab_unit_id: int | None = None) -> bool:
    return _allowed(
        db,
        user,
        project_id=project_id,
        lab_unit_id=lab_unit_id,
        roles={PROJECT_PI, SITE_PI, PROJECT_ADMIN, "optometrist"},
    )


def can_sync_remidio(db, user, *, project_id: int, lab_unit_id: int | None = None) -> bool:
    return has_remidio_sync_assignment(
        db,
        user_id=user.id,
        project_id=project_id,
        lab_unit_id=lab_unit_id,
    )


def allowed_project_lab_unit_ids(
    db,
    user,
    *,
    project_id: int,
    roles,
    allow_admin: bool = True,
) -> frozenset[int]:
    """Return configured Lab Units contained by the actor's named role grants."""
    from sqlalchemy import select

    from data_authorization.models import ProjectRoleGrant
    from models import Role
    from project_configuration.models import ProjectLabUnit

    configured = frozenset(
        db.execute(
            select(ProjectLabUnit.lab_unit_id).where(
                ProjectLabUnit.project_id == project_id,
                ProjectLabUnit.active.is_(True),
            )
        ).scalars()
    )
    context = access_context(db, user)
    if allow_admin and admin_scope(context).allowed:
        return configured
    grants = db.execute(
        select(ProjectRoleGrant.scope_type, ProjectRoleGrant.lab_unit_id)
        .join(Role, Role.id == ProjectRoleGrant.role_id)
        .where(
            ProjectRoleGrant.project_id == project_id,
            ProjectRoleGrant.user_id == user.id,
            ProjectRoleGrant.active.is_(True),
            Role.name.in_(frozenset(roles)),
        )
    ).all()
    if any(scope_type == "project" for scope_type, _ in grants):
        return configured
    return frozenset(
        lab_unit_id
        for scope_type, lab_unit_id in grants
        if scope_type == "lab_unit" and lab_unit_id in configured
    )


@dataclass(frozen=True)
class ProjectCapabilities:
    project_id: int
    can_view: bool
    can_view_overview: bool
    can_browse: bool
    can_browse_pii: bool
    can_manage_access: bool
    can_manage_uploaders: bool
    can_run_wai: bool
    can_view_wai_results: bool
    upload_kinds: frozenset[str]
    can_sync_remidio: bool


def project_capabilities(db, *, user, project_id: int) -> ProjectCapabilities:
    kinds = frozenset(
        kind
        for kind in ("direct_image", "pregraded", "remidio", "encounter_set")
        if has_upload_assignment(
            db,
            user_id=user.id,
            project_id=project_id,
            upload_kinds={kind},
        )
    )
    can_view = can_view_project(db, user, project_id=project_id)
    return ProjectCapabilities(
        project_id=project_id,
        can_view=can_view,
        can_view_overview=can_view,
        can_browse=can_browse_project(db, user, project_id=project_id),
        can_browse_pii=can_browse_project_pii(db, user, project_id=project_id),
        can_manage_access=can_manage_project_access(db, user, project_id=project_id),
        can_manage_uploaders=can_manage_project_uploaders(db, user, project_id=project_id),
        can_run_wai=can_run_wai(db, user, project_id=project_id),
        can_view_wai_results=can_view_wai_results(db, user, project_id=project_id),
        upload_kinds=kinds,
        can_sync_remidio=can_sync_remidio(db, user, project_id=project_id),
    )
