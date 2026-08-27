"""Current-user capability, workspace, and upload-option projections."""

from __future__ import annotations

from sqlalchemy import select

from authz_v2.core.actions import Action
from authz_v2.core.catalogue import CATALOGUE
from authz_v2.core.choices import CapabilityDTO, UploadOptionDTO, WorkspaceOptionDTO
from authz_v2.core.principals import PrincipalDTO
from authz_v2.core.resources import DisclosureClass, ScopeDTO
from authz_v2.core.roles import Role, ScopeType
from authz_v2.domain.models import AuthorizationUploadProfileAssignment
from authz_v2.repositories.contracts import GrantRecord
from authz_v2.services.listing import applicable_grants
from models import LabUnit, Project
from project_configuration.models import ProjectLabUnit
from upload_profiles.models import (
    ProjectUploadProfile,
    ProjectUploadProfileAssignment,
    UploadProfile,
)

SELF_ACTIONS = frozenset(
    {
        Action.ACCOUNT_PROFILE_VIEW,
        Action.ACCOUNT_PROFILE_UPDATE,
        Action.ACCOUNT_PASSWORD_CHANGE,
        Action.ACCOUNT_NOTIFICATIONS_VIEW,
        Action.ACCOUNT_NOTIFICATIONS_UPDATE,
        Action.ACCOUNT_MOBILE_SESSIONS_VIEW,
        Action.ACCOUNT_MOBILE_SESSIONS_REVOKE,
        Action.ACCOUNT_VIEWER_PREFERENCES_MANAGE,
        Action.AUTH_LOGOUT,
        Action.AUTH_REAUTH,
        Action.AUTHORIZATION_ME_CAPABILITIES_VIEW,
        Action.AUTHORIZATION_ME_UPLOAD_OPTIONS_VIEW,
        Action.AUTHORIZATION_ME_WORKSPACES_VIEW,
        Action.MOBILE_CONTEXT_VIEW,
    }
)

CLASSICAL_UPLOAD_ACTIONS = (
    Action.UPLOAD_CREATE,
    Action.UPLOAD_PREGRADED_CREATE,
)
PROJECT_UPLOAD_ACTIONS = (
    Action.PROJECT_UPLOAD_CREATE,
    Action.PROJECT_UPLOAD_PREGRADED,
    Action.GLAUCOMA_AI_UPLOAD_CREATE,
    Action.MOBILE_UPLOAD_CREATE,
)


def capability_projection(
    principal: PrincipalDTO, grants: tuple[GrantRecord, ...]
) -> tuple[CapabilityDTO, ...]:
    """Return potential usable actions without claiming exact-resource admission."""
    if principal.user_id is None or not principal.active or not principal.authenticated:
        return ()
    capabilities = []
    for action, definition in sorted(CATALOGUE.items(), key=lambda item: item[0].value):
        if definition.authorization_paths[0][0] == "public":
            continue
        relevant = applicable_grants(action, grants)
        if action in SELF_ACTIONS:
            scopes = ()
        elif not relevant:
            continue
        elif definition.disclosure_class is DisclosureClass.IDENTIFIER_RELEASE:
            pii_grants = tuple(
                grant for grant in grants if grant.role is Role.PII_EXPORTER
            )
            if not any(
                ordinary.scope.contains(
                    pii.scope,
                    allow_system=ordinary.role is Role.ADMIN
                    and ordinary.scope.scope_type is ScopeType.SYSTEM,
                )
                or pii.scope.contains(ordinary.scope)
                for ordinary in relevant
                for pii in pii_grants
            ):
                continue
            scopes = tuple(sorted({grant.scope.scope_type.value for grant in relevant}))
        else:
            scopes = tuple(sorted({grant.scope.scope_type.value for grant in relevant}))
        capabilities.append(CapabilityDTO(action.value, True, scopes))
    return tuple(capabilities)


def _grant_reaches(grants: tuple[GrantRecord, ...], scope) -> bool:
    return any(
        grant.scope.contains(
            scope,
            allow_system=grant.role is Role.ADMIN
            and grant.scope.scope_type is ScopeType.SYSTEM,
        )
        for grant in grants
    )


def _grants_for_actions(
    actions: tuple[Action, ...], grants: tuple[GrantRecord, ...]
) -> tuple[GrantRecord, ...]:
    """Return grants eligible for at least one action without duplicating rows."""
    eligible: dict[int, GrantRecord] = {}
    for action in actions:
        eligible.update(
            (grant.grant_id, grant) for grant in applicable_grants(action, grants)
        )
    return tuple(eligible.values())


def workspace_projection(
    db, grants: tuple[GrantRecord, ...]
) -> tuple[WorkspaceOptionDTO, ...]:
    """Return only active stored classical and project workspaces in reach."""
    options: dict[str, WorkspaceOptionDTO] = {}
    admin_global = any(
        grant.role is Role.ADMIN and grant.scope.scope_type is ScopeType.SYSTEM
        for grant in grants
    )

    lab_ids = {
        grant.scope.lab_unit_id or grant.scope.scope_id
        for grant in grants
        if grant.scope.scope_type is ScopeType.LAB_UNIT
    }
    hospital_ids = {
        grant.scope.hospital_id or grant.scope.scope_id
        for grant in grants
        if grant.scope.scope_type is ScopeType.HOSPITAL
    }
    lab_query = select(LabUnit)
    if not admin_global:
        clauses = []
        if lab_ids:
            clauses.append(LabUnit.id.in_(lab_ids))
        if hospital_ids:
            clauses.append(LabUnit.hospital_id.in_(hospital_ids))
        if not clauses:
            lab_query = lab_query.where(False)
        else:
            from sqlalchemy import or_

            lab_query = lab_query.where(or_(*clauses))
    for lab in db.execute(lab_query.order_by(LabUnit.id)).scalars():
        options[f"lab:{lab.id}"] = WorkspaceOptionDTO(
            f"lab:{lab.id}",
            lab.name,
            ScopeType.LAB_UNIT.value,
            hospital_id=lab.hospital_id,
            lab_unit_id=lab.id,
        )

    project_ids = {
        grant.scope.project_id or grant.scope.scope_id
        for grant in grants
        if grant.scope.scope_type is ScopeType.PROJECT
    }
    site_ids = {
        grant.scope.project_lab_unit_id or grant.scope.scope_id
        for grant in grants
        if grant.scope.scope_type is ScopeType.PROJECT_LAB_UNIT
    }
    site_query = select(ProjectLabUnit)
    if not admin_global:
        from sqlalchemy import or_

        clauses = []
        if project_ids:
            clauses.append(ProjectLabUnit.project_id.in_(project_ids))
        if site_ids:
            clauses.append(ProjectLabUnit.id.in_(site_ids))
        site_query = (
            site_query.where(or_(*clauses)) if clauses else site_query.where(False)
        )
    sites = tuple(
        db.execute(
            site_query.where(ProjectLabUnit.active.is_(True)).order_by(
                ProjectLabUnit.id
            )
        ).scalars()
    )
    projects = {
        project.id: project
        for project in db.execute(
            select(Project).where(Project.id.in_({site.project_id for site in sites}))
        ).scalars()
    }
    labs = {
        lab.id: lab
        for lab in db.execute(
            select(LabUnit).where(LabUnit.id.in_({site.lab_unit_id for site in sites}))
        ).scalars()
    }
    for site in sites:
        project = projects.get(site.project_id)
        lab = labs.get(site.lab_unit_id)
        if project is None or lab is None or not project.active:
            continue
        options[f"project_site:{site.id}"] = WorkspaceOptionDTO(
            f"project_site:{site.id}",
            f"{project.title} - {lab.name}",
            ScopeType.PROJECT_LAB_UNIT.value,
            project_id=project.id,
            hospital_id=lab.hospital_id,
            lab_unit_id=lab.id,
        )
    return tuple(options[key] for key in sorted(options))


def upload_projection(
    db, principal: PrincipalDTO, grants: tuple[GrantRecord, ...]
) -> tuple[UploadOptionDTO, ...]:
    """Return exact active assignment/profile options already in grant reach."""
    if principal.user_id is None:
        return ()
    options: list[UploadOptionDTO] = []
    classical_upload_grants = _grants_for_actions(CLASSICAL_UPLOAD_ACTIONS, grants)
    project_upload_grants = _grants_for_actions(PROJECT_UPLOAD_ACTIONS, grants)
    classical = tuple(
        db.execute(
            select(AuthorizationUploadProfileAssignment).where(
                AuthorizationUploadProfileAssignment.user_id == principal.user_id,
                AuthorizationUploadProfileAssignment.active.is_(True),
            )
        ).scalars()
    )
    project = tuple(
        db.execute(
            select(ProjectUploadProfileAssignment).where(
                ProjectUploadProfileAssignment.user_id == principal.user_id,
                ProjectUploadProfileAssignment.active.is_(True),
            )
        ).scalars()
    )
    profile_ids = {row.upload_profile_id for row in classical}
    project_profile_ids = {row.project_upload_profile_id for row in project}
    project_profiles = {
        row.id: row
        for row in db.execute(
            select(ProjectUploadProfile).where(
                ProjectUploadProfile.id.in_(project_profile_ids),
                ProjectUploadProfile.active.is_(True),
            )
        ).scalars()
    }
    profile_ids.update(row.upload_profile_id for row in project_profiles.values())
    profiles = {
        row.id: row
        for row in db.execute(
            select(UploadProfile).where(
                UploadProfile.id.in_(profile_ids), UploadProfile.active.is_(True)
            )
        ).scalars()
    }
    labs = {
        row.id: row
        for row in db.execute(
            select(LabUnit).where(
                LabUnit.id.in_({row.lab_unit_id for row in (*classical, *project)})
            )
        ).scalars()
    }

    for assignment in classical:
        lab = labs.get(assignment.lab_unit_id)
        profile = profiles.get(assignment.upload_profile_id)
        if lab is None or profile is None:
            continue
        scope = ScopeDTO(
            ScopeType.LAB_UNIT,
            lab.id,
            hospital_id=lab.hospital_id,
            lab_unit_id=lab.id,
        )
        if not _grant_reaches(classical_upload_grants, scope):
            continue
        options.append(
            UploadOptionDTO(
                f"classical:{assignment.id}",
                f"{lab.name} - {profile.name}",
                ScopeType.LAB_UNIT.value,
                hospital_id=lab.hospital_id,
                lab_unit_id=lab.id,
                upload_profile_id=profile.id,
            )
        )

    project_ids = {row.project_id for row in project_profiles.values()}
    projects = {
        row.id: row
        for row in db.execute(
            select(Project).where(Project.id.in_(project_ids))
        ).scalars()
    }
    project_sites = {
        (row.project_id, row.lab_unit_id): row
        for row in db.execute(
            select(ProjectLabUnit).where(
                ProjectLabUnit.project_id.in_(project_ids),
                ProjectLabUnit.active.is_(True),
            )
        ).scalars()
    }
    for assignment in project:
        mapping = project_profiles.get(assignment.project_upload_profile_id)
        if mapping is None:
            continue
        profile = profiles.get(mapping.upload_profile_id)
        lab = labs.get(assignment.lab_unit_id)
        project_row = projects.get(mapping.project_id)
        site = project_sites.get((mapping.project_id, assignment.lab_unit_id))
        if profile is None or lab is None or project_row is None or site is None:
            continue
        scope = ScopeDTO(
            ScopeType.PROJECT_LAB_UNIT,
            site.id,
            hospital_id=lab.hospital_id,
            lab_unit_id=lab.id,
            project_id=project_row.id,
            project_lab_unit_id=site.id,
        )
        if not project_row.active or not _grant_reaches(project_upload_grants, scope):
            continue
        options.append(
            UploadOptionDTO(
                f"project:{assignment.id}",
                f"{project_row.title} - {lab.name} - {profile.name}",
                ScopeType.PROJECT_LAB_UNIT.value,
                project_id=project_row.id,
                hospital_id=lab.hospital_id,
                lab_unit_id=lab.id,
                upload_profile_id=profile.id,
            )
        )
    return tuple(sorted(options, key=lambda item: str(item.id)))
