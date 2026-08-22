"""Canonical project action policy and cached persisted evaluation.

Project grants authorize project-owned resources only.  Global application
roles continue to authorize projectless legacy workflows through their existing
policies; they are deliberately not consulted here (except ``admin``).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.orm import Session, aliased

from authz.cache import get_cached_decision, set_cached_decision
from authz.types import AuthzDecision, GrantSource, ResourceRef
from models import LabUnit, ProjectInvestigator, Role
from upload_profiles.models import (
    ProjectUploadProfile,
    ProjectUploadProfileAssignment,
    UploadProfile,
    UploadProfileKind,
)
from project_configuration.models import ProjectLabUnit
from project_configuration.service import configured_project_lab_unit_ids

from .models import HOSPITAL_SCOPE, LAB_UNIT_SCOPE, PROJECT_SCOPE, ProjectRoleGrant


ROLE_PROJECT_PI = "project_pi"
ROLE_SITE_PI = "site_pi"
ROLE_PROJECT_ADMIN = "project_admin"
ROLE_COLLABORATOR = "collaborator"
ROLE_VERIFIER = "verifier"
ROLE_OPHTHALMOLOGIST = "ophthalmologist"
ROLE_OPTOMETRIST = "optometrist"
ROLE_ANALYTICS_VIEWER = "analytics_viewer"
ROLE_DATASET_CREATOR = "dataset_creator"
ROLE_DATA_EXPORTER = "data_exporter"
ROLE_DISCREPANCY_REVIEWER = "discrepancy_reviewer"
ROLE_REGRADE_ADJUDICATOR = "regrade_adjudicator"

PROJECT_GOVERNANCE_ROLE_NAMES = frozenset({
    ROLE_PROJECT_PI,
    ROLE_SITE_PI,
    ROLE_PROJECT_ADMIN,
})
PROJECT_OPERATIONAL_ROLE_NAMES = frozenset({
    ROLE_COLLABORATOR,
    ROLE_VERIFIER,
    ROLE_OPHTHALMOLOGIST,
    ROLE_OPTOMETRIST,
    ROLE_ANALYTICS_VIEWER,
    ROLE_DATASET_CREATOR,
    ROLE_DATA_EXPORTER,
    ROLE_DISCREPANCY_REVIEWER,
    ROLE_REGRADE_ADJUDICATOR,
})
PROJECT_ASSIGNABLE_ROLE_NAMES = PROJECT_GOVERNANCE_ROLE_NAMES | PROJECT_OPERATIONAL_ROLE_NAMES
PROJECT_ADMIN_ASSIGNABLE_ROLE_NAMES = PROJECT_OPERATIONAL_ROLE_NAMES
PROJECT_ONLY_ROLE_NAMES = PROJECT_GOVERNANCE_ROLE_NAMES | frozenset({ROLE_COLLABORATOR})
PROJECT_WIDE_GOVERNANCE_ROLE_NAMES = frozenset({ROLE_PROJECT_PI, ROLE_PROJECT_ADMIN})

LEGACY_PROJECT_ROLE_ALIASES = {
    ROLE_PROJECT_PI: frozenset({"principal_investigator"}),
    ROLE_COLLABORATOR: frozenset({"collaborator", "co_investigator", "coordinator"}),
}

ACTION_VIEW = "project.view"
ACTION_BROWSE = "project.encountersets.browse"
ACTION_BROWSE_PII = "project.encountersets.browse_pii"
ACTION_MANAGE_ACCESS = "project.access.manage"
ACTION_MANAGE_UPLOADERS = "project.uploaders.manage"
ACTION_WAI_RUN = "project.wai.run"
ACTION_WAI_RESULTS = "project.wai.results"
ACTION_UPLOAD_DIRECT = "project.upload.direct_image"
ACTION_UPLOAD_PREGRADED = "project.upload.pregraded"
ACTION_UPLOAD_REMIDIO_ZIP = "project.upload.remidio"
ACTION_UPLOAD_ENCOUNTER_SET = "project.upload.encounter_set"
ACTION_REMIDIO_SYNC = "project.upload.remidio_api_sync"

UPLOAD_ACTION_KIND = {
    ACTION_UPLOAD_DIRECT: "direct_image",
    ACTION_UPLOAD_PREGRADED: "pregraded",
    ACTION_UPLOAD_REMIDIO_ZIP: "remidio",
    ACTION_UPLOAD_ENCOUNTER_SET: "encounter_set",
}

ACTION_ROLE_NAMES = {
    ACTION_VIEW: PROJECT_ASSIGNABLE_ROLE_NAMES,
    ACTION_BROWSE: PROJECT_ASSIGNABLE_ROLE_NAMES,
    ACTION_BROWSE_PII: PROJECT_ASSIGNABLE_ROLE_NAMES - {ROLE_COLLABORATOR},
    ACTION_MANAGE_ACCESS: frozenset({ROLE_PROJECT_ADMIN}),
    ACTION_MANAGE_UPLOADERS: frozenset({ROLE_PROJECT_ADMIN}),
    ACTION_WAI_RUN: frozenset({ROLE_VERIFIER, ROLE_OPTOMETRIST}),
    ACTION_WAI_RESULTS: frozenset({
        ROLE_PROJECT_PI,
        ROLE_SITE_PI,
        ROLE_PROJECT_ADMIN,
        ROLE_OPTOMETRIST,
    }),
}


@dataclass(frozen=True)
class ProjectCapabilities:
    """Menu-safe summary; resource routes must still check the exact scope."""

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


@dataclass(frozen=True)
class ProjectResourceScope:
    project_id: int | None
    hospital_id: int | None
    lab_unit_id: int | None


def project_capabilities(db: Session, *, user: Any, project_id: int) -> ProjectCapabilities:
    upload_kinds = frozenset(
        kind
        for action, kind in UPLOAD_ACTION_KIND.items()
        if user_can_project_action(db, user=user, project_id=project_id, action=action)
    )
    return ProjectCapabilities(
        project_id=project_id,
        can_view=user_can_project_action(db, user=user, project_id=project_id, action=ACTION_VIEW),
        can_view_overview=(
            user.has_role("admin")
            or _has_project_role(
                db,
                user_id=user.id,
                project_id=project_id,
                role_names=PROJECT_ASSIGNABLE_ROLE_NAMES,
                hospital_id=None,
                lab_unit_id=None,
            )
        ),
        can_browse=user_can_project_action(db, user=user, project_id=project_id, action=ACTION_BROWSE),
        can_browse_pii=user_can_project_action(db, user=user, project_id=project_id, action=ACTION_BROWSE_PII),
        can_manage_access=user_can_project_action(db, user=user, project_id=project_id, action=ACTION_MANAGE_ACCESS),
        can_manage_uploaders=user_can_project_action(db, user=user, project_id=project_id, action=ACTION_MANAGE_UPLOADERS),
        can_run_wai=user_can_project_action(db, user=user, project_id=project_id, action=ACTION_WAI_RUN),
        can_view_wai_results=user_can_project_action(db, user=user, project_id=project_id, action=ACTION_WAI_RESULTS),
        upload_kinds=upload_kinds,
        can_sync_remidio=user_can_project_action(db, user=user, project_id=project_id, action=ACTION_REMIDIO_SYNC),
    )


def user_can_project_action(
    db: Session,
    *,
    user: Any,
    project_id: int,
    action: str,
    hospital_id: int | None = None,
    lab_unit_id: int | None = None,
) -> bool:
    """Evaluate one project action from persisted grants/assignments with Redis caching."""
    if not getattr(user, "is_authenticated", True):
        return False
    user_id = int(user.id)
    resource = ResourceRef(
        type="project",
        id=project_id,
        attributes={
            "project_id": project_id,
            "hospital_id": hospital_id,
            "lab_unit_id": lab_unit_id,
        },
    )
    cached = get_cached_decision(user_id=user_id, action=action, resource=resource)
    if cached is not None:
        return cached.allowed

    configured_lab_ids = configured_project_lab_unit_ids(db, project_id=project_id)
    if lab_unit_id is not None and lab_unit_id not in configured_lab_ids:
        decision = AuthzDecision.deny(action, "lab_unit_outside_project_boundary")
        set_cached_decision(user_id=user_id, action=action, resource=resource, decision=decision)
        return False
    if hospital_id is not None:
        configured_hospital_ids = set(db.execute(
            select(LabUnit.hospital_id).where(LabUnit.id.in_(configured_lab_ids or {-1}))
        ).scalars())
        if hospital_id not in configured_hospital_ids:
            decision = AuthzDecision.deny(action, "hospital_outside_project_boundary")
            set_cached_decision(user_id=user_id, action=action, resource=resource, decision=decision)
            return False

    if user.has_role("admin"):
        allowed = True
        source = GrantSource.ADMIN_GLOBAL
    elif action in UPLOAD_ACTION_KIND:
        allowed = _has_upload_assignment(
            db,
            user_id=user_id,
            project_id=project_id,
            upload_kind=UPLOAD_ACTION_KIND[action],
            hospital_id=hospital_id,
            lab_unit_id=lab_unit_id,
        )
        source = GrantSource.UPLOAD_PROFILE
    elif action == ACTION_REMIDIO_SYNC:
        allowed = _has_remidio_sync_assignment(
            db,
            user_id=user_id,
            project_id=project_id,
            hospital_id=hospital_id,
            lab_unit_id=lab_unit_id,
        )
        source = GrantSource.UPLOAD_PROFILE
    elif action == ACTION_VIEW:
        roles = ACTION_ROLE_NAMES[action]
        allowed = _has_project_role(
            db,
            user_id=user_id,
            project_id=project_id,
            role_names=roles,
            hospital_id=hospital_id,
            lab_unit_id=lab_unit_id,
        ) or _has_any_upload_assignment(
            db,
            user_id=user_id,
            project_id=project_id,
            hospital_id=hospital_id,
            lab_unit_id=lab_unit_id,
        )
        source = GrantSource.PROJECT_ROLE
    else:
        roles = ACTION_ROLE_NAMES.get(action, frozenset())
        allowed = bool(roles) and _has_project_role(
            db,
            user_id=user_id,
            project_id=project_id,
            role_names=roles,
            hospital_id=hospital_id,
            lab_unit_id=lab_unit_id,
        )
        source = GrantSource.PROJECT_ROLE

    decision = (
        AuthzDecision.allow(action, source)
        if allowed
        else AuthzDecision.deny(action, "missing_scoped_project_authority")
    )
    set_cached_decision(user_id=user_id, action=action, resource=resource, decision=decision)
    return allowed


def grading_task_project_scope(db: Session, *, task_id: int) -> ProjectResourceScope | None:
    """Resolve the project and Lab Unit owned by one polymorphic grading task."""
    from models import (
        DirectImageUpload,
        EncounterFile,
        EncounterSetImage,
        GradingTask,
        PatientEncounters,
    )

    task = db.get(GradingTask, task_id)
    if task is None:
        return None
    project_id = None
    lab_unit_id = task.lab_unit_id
    task_lab = db.get(LabUnit, lab_unit_id)
    hospital_id = task_lab.hospital_id if task_lab else None
    if task.patient_encounter_id:
        encounter = db.get(PatientEncounters, task.patient_encounter_id)
        project_id = encounter.project_id if encounter else None
        hospital_id = encounter.hospital_id if encounter else hospital_id
        lab_unit_id = encounter.lab_unit_id if encounter else lab_unit_id
    elif task.encounter_set_image_id:
        image = db.get(EncounterSetImage, task.encounter_set_image_id)
        encounter = db.get(PatientEncounters, image.patient_encounter_id) if image else None
        project_id = (image.project_id if image else None) or (
            encounter.project_id if encounter else None
        )
        hospital_id = encounter.hospital_id if encounter else hospital_id
        lab_unit_id = encounter.lab_unit_id if encounter else lab_unit_id
    elif task.encounter_file_id:
        image = db.get(EncounterFile, task.encounter_file_id)
        encounter = db.get(PatientEncounters, image.patient_encounter_id) if image else None
        project_id = (image.project_id if image else None) or (
            encounter.project_id if encounter else None
        )
        hospital_id = encounter.hospital_id if encounter else hospital_id
        lab_unit_id = encounter.lab_unit_id if encounter else lab_unit_id
    elif task.direct_image_upload_id:
        image = db.get(DirectImageUpload, task.direct_image_upload_id)
        project_id = image.project_id if image else None
        hospital_id = image.hospital_id if image else hospital_id
        lab_unit_id = image.lab_unit_id if image else lab_unit_id
    return ProjectResourceScope(
        project_id=project_id,
        hospital_id=hospital_id,
        lab_unit_id=lab_unit_id,
    )


def allowed_lab_unit_ids_for_action(
    db: Session,
    *,
    user: Any,
    project_id: int,
    action: str,
) -> frozenset[int]:
    """Return allowed Lab Units, always intersected with project configuration."""
    configured_lab_ids = configured_project_lab_unit_ids(db, project_id=project_id)
    if user.has_role("admin"):
        return configured_lab_ids
    roles = ACTION_ROLE_NAMES.get(action, frozenset())
    if not roles:
        return frozenset()
    grants = db.execute(
        select(ProjectRoleGrant.scope_type, ProjectRoleGrant.hospital_id, ProjectRoleGrant.lab_unit_id)
        .join(Role, Role.id == ProjectRoleGrant.role_id)
        .where(
            ProjectRoleGrant.user_id == user.id,
            ProjectRoleGrant.project_id == project_id,
            ProjectRoleGrant.active.is_(True),
            Role.name.in_(_expanded_role_names(roles)),
        )
    ).all()
    project_wide_governance_names = roles.intersection(PROJECT_WIDE_GOVERNANCE_ROLE_NAMES)
    if project_wide_governance_names and db.execute(
        select(ProjectRoleGrant.id)
        .join(Role, Role.id == ProjectRoleGrant.role_id)
        .where(
            ProjectRoleGrant.user_id == user.id,
            ProjectRoleGrant.project_id == project_id,
            ProjectRoleGrant.active.is_(True),
            Role.name.in_(_expanded_role_names(project_wide_governance_names)),
        )
        .limit(1)
    ).scalar_one_or_none() is not None:
        return configured_lab_ids
    if _has_legacy_project_role(
        db,
        user_id=int(user.id),
        project_id=project_id,
        role_names=roles,
    ):
        return configured_lab_ids
    if any(scope_type == PROJECT_SCOPE for scope_type, _, _ in grants):
        return configured_lab_ids
    lab_ids = {lab_id for scope_type, _, lab_id in grants if scope_type == LAB_UNIT_SCOPE and lab_id}
    hospital_ids = {hospital_id for scope_type, hospital_id, _ in grants if scope_type == HOSPITAL_SCOPE and hospital_id}
    if hospital_ids:
        lab_ids.update(db.execute(select(LabUnit.id).where(LabUnit.hospital_id.in_(hospital_ids))).scalars())
    return frozenset(lab_ids).intersection(configured_lab_ids)


def user_has_any_project_upload_assignment(
    db: Session,
    *,
    user: Any,
    upload_kinds: frozenset[str],
) -> bool:
    """Return whether a user has an active assignment for any requested upload kind.

    This is a coarse page/API entry gate.  The upload service remains responsible
    for validating the exact project, profile, hospital, lab unit, and clinical
    options selected by the request.
    """
    if not getattr(user, "is_authenticated", True):
        return False
    if user.has_role("admin", "fileUploader"):
        return True
    if not upload_kinds:
        return False

    action = "project.upload.entry:" + ",".join(sorted(upload_kinds))
    resource = ResourceRef(type="upload_entry", id=0, attributes={})
    cached = get_cached_decision(user_id=int(user.id), action=action, resource=resource)
    if cached is not None:
        return cached.allowed

    allowed = db.execute(
        _base_assignment_query(user_id=int(user.id), project_id=None)
        .join(UploadProfileKind, UploadProfileKind.upload_profile_id == UploadProfile.id)
        .where(UploadProfileKind.upload_kind.in_(upload_kinds))
        .limit(1)
    ).scalar_one_or_none() is not None
    decision = (
        AuthzDecision.allow(action, GrantSource.UPLOAD_PROFILE)
        if allowed
        else AuthzDecision.deny(action, "missing_upload_profile_assignment")
    )
    set_cached_decision(user_id=int(user.id), action=action, resource=resource, decision=decision)
    return allowed


def _scope_conditions(*, grant, hospital_id: int | None, lab_unit_id: int | None):
    conditions = [grant.scope_type == PROJECT_SCOPE]
    if hospital_id is not None:
        conditions.append(and_(grant.scope_type == HOSPITAL_SCOPE, grant.hospital_id == hospital_id))
    if lab_unit_id is not None:
        conditions.append(and_(grant.scope_type == LAB_UNIT_SCOPE, grant.lab_unit_id == lab_unit_id))
        lab = aliased(LabUnit)
        conditions.append(and_(
            grant.scope_type == HOSPITAL_SCOPE,
            exists().where(lab.id == lab_unit_id, lab.hospital_id == grant.hospital_id),
        ))
    if hospital_id is None and lab_unit_id is None:
        conditions.extend((grant.scope_type == HOSPITAL_SCOPE, grant.scope_type == LAB_UNIT_SCOPE))
    return conditions


def _has_project_role(
    db: Session,
    *,
    user_id: int,
    project_id: int,
    role_names: frozenset[str],
    hospital_id: int | None,
    lab_unit_id: int | None,
) -> bool:
    grant = aliased(ProjectRoleGrant)
    project_wide_governance_names = role_names.intersection(PROJECT_WIDE_GOVERNANCE_ROLE_NAMES)
    if project_wide_governance_names and db.execute(
        select(grant.id)
        .join(Role, Role.id == grant.role_id)
        .where(
            grant.user_id == user_id,
            grant.project_id == project_id,
            grant.active.is_(True),
            Role.name.in_(_expanded_role_names(project_wide_governance_names)),
        )
        .limit(1)
    ).scalar_one_or_none() is not None:
        return True
    persisted_grant = db.execute(
        select(grant.id)
        .join(Role, Role.id == grant.role_id)
        .where(
            grant.user_id == user_id,
            grant.project_id == project_id,
            grant.active.is_(True),
            Role.name.in_(_expanded_role_names(role_names)),
            or_(*_scope_conditions(grant=grant, hospital_id=hospital_id, lab_unit_id=lab_unit_id)),
        )
        .limit(1)
    ).scalar_one_or_none() is not None
    return persisted_grant or _has_legacy_project_role(
        db,
        user_id=user_id,
        project_id=project_id,
        role_names=role_names,
    )


def _expanded_role_names(role_names: frozenset[str]) -> frozenset[str]:
    expanded = set(role_names)
    for canonical_name in role_names:
        expanded.update(LEGACY_PROJECT_ROLE_ALIASES.get(canonical_name, ()))
    return frozenset(expanded)


def _has_legacy_project_role(
    db: Session,
    *,
    user_id: int,
    project_id: int,
    role_names: frozenset[str],
) -> bool:
    legacy_names = {
        legacy_name
        for canonical_name in role_names
        for legacy_name in LEGACY_PROJECT_ROLE_ALIASES.get(canonical_name, ())
    }
    if not legacy_names:
        return False
    return db.execute(
        select(ProjectInvestigator.id)
        .where(
            ProjectInvestigator.user_id == user_id,
            ProjectInvestigator.project_id == project_id,
            ProjectInvestigator.active.is_(True),
            ProjectInvestigator.role.in_(legacy_names),
        )
        .limit(1)
    ).scalar_one_or_none() is not None


def _assignment_scope_clause(*, hospital_id: int | None, lab_unit_id: int | None):
    if lab_unit_id is not None:
        return ProjectUploadProfileAssignment.lab_unit_id == lab_unit_id
    if hospital_id is not None:
        return exists().where(
            LabUnit.id == ProjectUploadProfileAssignment.lab_unit_id,
            LabUnit.hospital_id == hospital_id,
        )
    return True


def _base_assignment_query(*, user_id: int, project_id: int | None):
    query = (
        select(ProjectUploadProfileAssignment.id)
        .join(ProjectUploadProfile, ProjectUploadProfile.id == ProjectUploadProfileAssignment.project_upload_profile_id)
        .join(UploadProfile, UploadProfile.id == ProjectUploadProfile.upload_profile_id)
        .join(
            ProjectLabUnit,
            (ProjectLabUnit.project_id == ProjectUploadProfile.project_id)
            & (ProjectLabUnit.lab_unit_id == ProjectUploadProfileAssignment.lab_unit_id)
            & ProjectLabUnit.active.is_(True),
        )
        .where(
            ProjectUploadProfileAssignment.user_id == user_id,
            ProjectUploadProfileAssignment.active.is_(True),
            ProjectUploadProfile.active.is_(True),
            UploadProfile.active.is_(True),
        )
    )
    if project_id is not None:
        query = query.where(ProjectUploadProfile.project_id == project_id)
    return query


def _has_upload_assignment(
    db: Session,
    *,
    user_id: int,
    project_id: int,
    upload_kind: str,
    hospital_id: int | None,
    lab_unit_id: int | None,
) -> bool:
    query = (
        _base_assignment_query(user_id=user_id, project_id=project_id)
        .join(UploadProfileKind, UploadProfileKind.upload_profile_id == UploadProfile.id)
        .where(
            UploadProfileKind.upload_kind == upload_kind,
            _assignment_scope_clause(hospital_id=hospital_id, lab_unit_id=lab_unit_id),
        )
        .limit(1)
    )
    return db.execute(query).scalar_one_or_none() is not None


def _has_any_upload_assignment(
    db: Session,
    *,
    user_id: int,
    project_id: int,
    hospital_id: int | None,
    lab_unit_id: int | None,
) -> bool:
    query = (
        _base_assignment_query(user_id=user_id, project_id=project_id)
        .where(_assignment_scope_clause(hospital_id=hospital_id, lab_unit_id=lab_unit_id))
        .limit(1)
    )
    return db.execute(query).scalar_one_or_none() is not None


def _has_remidio_sync_assignment(
    db: Session,
    *,
    user_id: int,
    project_id: int,
    hospital_id: int | None,
    lab_unit_id: int | None,
) -> bool:
    from remidio_api_integration.models import ProjectUploadProfileRemidioApiBinding

    binding = ProjectUploadProfileRemidioApiBinding
    query = (
        _base_assignment_query(user_id=user_id, project_id=project_id)
        .join(binding, binding.project_upload_profile_id == ProjectUploadProfile.id)
        .where(
            binding.active.is_(True),
            or_(binding.lab_unit_id.is_(None), binding.lab_unit_id == ProjectUploadProfileAssignment.lab_unit_id),
            _assignment_scope_clause(hospital_id=hospital_id, lab_unit_id=lab_unit_id),
        )
        .limit(1)
    )
    return db.execute(query).scalar_one_or_none() is not None
