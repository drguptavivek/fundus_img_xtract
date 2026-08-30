"""Named, role-bound single-resource authorization helpers."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import and_, or_, select

from authz.context import AccessContext
from authz.exceptions import AuthorizationDenied

_LOGGER = logging.getLogger("authorization")


class RecordWorld(StrEnum):
    SELF = "self"
    CLASSICAL = "classical"
    PROJECT = "project"
    GLOBAL = "global"


@dataclass(frozen=True)
class RecordScope:
    """Authoritative lineage for one resource or mutation target."""

    world: RecordWorld
    user_id: int | None = None
    project_id: int | None = None
    hospital_id: int | None = None
    lab_unit_id: int | None = None

    @classmethod
    def self(cls, user_id: int) -> RecordScope:
        return cls(world=RecordWorld.SELF, user_id=int(user_id))

    @classmethod
    def classical(cls, *, lab_unit_id: int, hospital_id: int) -> RecordScope:
        return cls(
            world=RecordWorld.CLASSICAL,
            lab_unit_id=int(lab_unit_id),
            hospital_id=int(hospital_id),
        )

    @classmethod
    def project(
        cls,
        *,
        project_id: int,
        lab_unit_id: int | None = None,
        hospital_id: int | None = None,
    ) -> RecordScope:
        return cls(
            world=RecordWorld.PROJECT,
            project_id=int(project_id),
            lab_unit_id=None if lab_unit_id is None else int(lab_unit_id),
            hospital_id=None if hospital_id is None else int(hospital_id),
        )

    @classmethod
    def global_resource(cls) -> RecordScope:
        return cls(world=RecordWorld.GLOBAL)


@dataclass(frozen=True)
class ScopeCheck:
    allowed: bool
    reason: str
    evidence: str | None = None


def _roles(values: Iterable[str]) -> frozenset[str]:
    return frozenset(str(value).strip().lower() for value in values if value)


def _deny(reason: str) -> ScopeCheck:
    return ScopeCheck(False, reason)


def _allow(evidence: str) -> ScopeCheck:
    return ScopeCheck(True, "allowed", evidence)


def require_any(*checks: ScopeCheck) -> ScopeCheck:
    """Require at least one complete role-scope path."""

    for check in checks:
        if check.allowed:
            return check
    reason = ",".join(dict.fromkeys(check.reason for check in checks)) or "no_scope_path"
    _LOGGER.warning("authorization denied reason=%s", reason)
    raise AuthorizationDenied(reason)


def require_all(*checks: ScopeCheck) -> tuple[ScopeCheck, ...]:
    """Require every independent authority, preserving same-target scoping."""

    denied = [check for check in checks if not check.allowed]
    if denied:
        reason = ",".join(dict.fromkeys(check.reason for check in denied))
        _LOGGER.warning("authorization denied reason=%s", reason)
        raise AuthorizationDenied(reason)
    return checks


def admin_scope(context: AccessContext) -> ScopeCheck:
    if context.has_any_global_role(frozenset({"admin"})):
        return _allow("admin_global")
    return _deny("admin_required")


def self_scope(context: AccessContext, user_id: int | None) -> ScopeCheck:
    if not context.active or user_id is None:
        return _deny("missing_self_scope")
    if context.user_id == int(user_id):
        return _allow("self")
    return _deny("not_self")


def assigned_lab_scope(
    context: AccessContext,
    roles: Iterable[str],
    record: RecordScope,
) -> ScopeCheck:
    allowed_roles = _roles(roles)
    if record.world != RecordWorld.CLASSICAL or record.lab_unit_id is None:
        return _deny("classical_lab_scope_required")
    if not context.has_any_global_role(allowed_roles):
        return _deny("global_role_required")
    if record.lab_unit_id in context.assigned_lab_unit_ids:
        return _allow("assigned_lab_unit")
    return _deny("lab_unit_not_assigned")


def _hospital_ids_for_roles(
    context: AccessContext, roles: frozenset[str]
) -> frozenset[int]:
    if (
        context.hospital_id is None
        or not context.has_any_global_role(roles)
    ):
        return frozenset()
    return frozenset({context.hospital_id})


def hospital_scope(
    context: AccessContext,
    roles: Iterable[str],
    record: RecordScope,
) -> ScopeCheck:
    allowed_roles = _roles(roles)
    if not context.active:
        return _deny("inactive_actor")
    if record.world != RecordWorld.CLASSICAL or record.hospital_id is None:
        return _deny("classical_hospital_scope_required")
    if record.hospital_id in _hospital_ids_for_roles(context, allowed_roles):
        return _allow("role_and_hospital_assignment")
    return _deny("hospital_role_scope_missing")


def _project_role_scope_matches(
    context: AccessContext,
    roles: frozenset[str],
    record: RecordScope,
    *,
    project_wide: bool,
) -> bool:
    if record.project_id is None:
        return False
    key = (
        "project_scope",
        tuple(sorted(roles)),
        record.project_id,
        record.lab_unit_id,
        project_wide,
    )
    cached = context.cache.get(key)
    if cached is not None:
        return bool(cached)

    from data_authorization.models import ProjectRoleGrant
    from models import Role
    from project_configuration.models import ProjectLabUnit

    conditions = [
        ProjectRoleGrant.user_id == context.user_id,
        ProjectRoleGrant.project_id == record.project_id,
        ProjectRoleGrant.active.is_(True),
        Role.name.in_(roles),
    ]
    if project_wide:
        conditions.extend(
            [
                ProjectRoleGrant.scope_type == "project",
                ProjectRoleGrant.lab_unit_id.is_(None),
            ]
        )
    elif record.lab_unit_id is None:
        # A project shell may be seen by any contained grant. Data below it is
        # still narrowed by the list query for that grant.
        conditions.append(
            or_(
                ProjectRoleGrant.scope_type == "project",
                and_(
                    ProjectRoleGrant.scope_type == "lab_unit",
                    ProjectRoleGrant.lab_unit_id.in_(
                        select(ProjectLabUnit.lab_unit_id).where(
                            ProjectLabUnit.project_id == record.project_id,
                            ProjectLabUnit.active.is_(True),
                        )
                    ),
                ),
            )
        )
    else:
        configured = context.db.execute(
            select(ProjectLabUnit.id).where(
                ProjectLabUnit.project_id == record.project_id,
                ProjectLabUnit.lab_unit_id == record.lab_unit_id,
                ProjectLabUnit.active.is_(True),
            )
        ).scalar_one_or_none()
        if configured is None:
            context.cache[key] = False
            return False
        conditions.append(
            or_(
                ProjectRoleGrant.scope_type == "project",
                and_(
                    ProjectRoleGrant.scope_type == "lab_unit",
                    ProjectRoleGrant.lab_unit_id == record.lab_unit_id,
                ),
            )
        )

    matched = context.db.execute(
        select(ProjectRoleGrant.id)
        .join(Role, Role.id == ProjectRoleGrant.role_id)
        .where(*conditions)
        .limit(1)
    ).scalar_one_or_none() is not None
    context.cache[key] = matched
    return matched


def project_scope(
    context: AccessContext,
    roles: Iterable[str],
    record: RecordScope,
) -> ScopeCheck:
    allowed_roles = _roles(roles)
    if not context.active:
        return _deny("inactive_actor")
    if record.world != RecordWorld.PROJECT or record.project_id is None:
        return _deny("project_scope_required")
    if _project_role_scope_matches(
        context, allowed_roles, record, project_wide=False
    ):
        return _allow("project_role_grant")
    return _deny("project_role_scope_missing")


def project_wide_scope(
    context: AccessContext,
    roles: Iterable[str],
    project_id: int | None,
) -> ScopeCheck:
    if project_id is None:
        return _deny("project_id_required")
    record = RecordScope.project(project_id=int(project_id))
    if _project_role_scope_matches(context, _roles(roles), record, project_wide=True):
        return _allow("project_wide_role_grant")
    return _deny("project_wide_role_required")


def upload_scope(
    context: AccessContext,
    roles: Iterable[str],
    record: RecordScope,
    *,
    upload_profile_id: int | None,
) -> ScopeCheck:
    """Require uploader qualification, location scope, and exact assignment."""

    if record.world == RecordWorld.CLASSICAL:
        return assigned_lab_scope(context, roles, record)
    if (
        record.world != RecordWorld.PROJECT
        or record.project_id is None
        or record.lab_unit_id is None
        or upload_profile_id is None
    ):
        return _deny("complete_upload_scope_required")

    # The exact active profile assignment is the project/location relationship;
    # requiring a second ProjectRoleGrant would duplicate the same fact.  The
    # uploader qualification remains an independent global role requirement.
    if not context.has_any_global_role(_roles(roles)):
        return _deny("upload_role_required")

    from upload_profiles.models import (
        ProjectUploadProfile,
        ProjectUploadProfileAssignment,
        UploadProfile,
    )

    assignment = context.db.execute(
        select(ProjectUploadProfileAssignment.id)
        .join(
            ProjectUploadProfile,
            ProjectUploadProfile.id
            == ProjectUploadProfileAssignment.project_upload_profile_id,
        )
        .join(UploadProfile, UploadProfile.id == ProjectUploadProfile.upload_profile_id)
        .where(
            ProjectUploadProfileAssignment.user_id == context.user_id,
            ProjectUploadProfileAssignment.lab_unit_id == record.lab_unit_id,
            ProjectUploadProfileAssignment.active.is_(True),
            ProjectUploadProfile.project_id == record.project_id,
            ProjectUploadProfile.upload_profile_id == int(upload_profile_id),
            ProjectUploadProfile.active.is_(True),
            UploadProfile.active.is_(True),
        )
        .limit(1)
    ).scalar_one_or_none()
    if assignment is None:
        return _deny("upload_assignment_required")
    return _allow("upload_profile_assignment")


_SLOT_COLUMNS = {
    "resident": "can_grade_resident",
    "resident2": "can_grade_resident2",
    "arbitrator": "can_arbitrate",
}


def grading_scope(
    context: AccessContext,
    record: RecordScope,
    *,
    disease_id: int | None,
    slot: str | None,
    allocation_scope: str | None = None,
    encounter_set_type_id: int | None = None,
) -> ScopeCheck:
    """Require the complete grading authority for the record's data world.

    Classical grading is authorised by the historical disease/Lab Unit slot
    assignment. Project grading is a separate authority: the actor must be a
    clinician and have an exact active project allocation for the requested
    target. A classical slot, project role, or Admin role cannot substitute for
    either path.
    """

    slot_name = str(slot or "").strip().lower()
    slot_column = _SLOT_COLUMNS.get(slot_name)
    if (
        disease_id is None
        or slot_column is None
        or record.lab_unit_id is None
    ):
        return _deny("complete_grading_scope_required")

    if record.world not in {RecordWorld.CLASSICAL, RecordWorld.PROJECT}:
        return _deny("grading_record_scope_required")

    clinical_roles = frozenset({"ophthalmologist", "field_ophthalmologist"})
    if not context.has_any_global_role(clinical_roles):
        return _deny("ophthalmologist_role_required")

    if record.world == RecordWorld.CLASSICAL:
        from models import UserDiseaseUnitRole

        slot_conditions = [
            UserDiseaseUnitRole.user_id == context.user_id,
            UserDiseaseUnitRole.disease_id == int(disease_id),
            UserDiseaseUnitRole.lab_unit_id == record.lab_unit_id,
            UserDiseaseUnitRole.active.is_(True),
            getattr(UserDiseaseUnitRole, slot_column).is_(True),
        ]
        if context.db.execute(
            select(UserDiseaseUnitRole.id).where(*slot_conditions).limit(1)
        ).scalar_one_or_none() is None:
            return _deny("grading_slot_required")
        return _allow("classical_grading_slot")

    if record.project_id is None:
        return _deny("project_id_required")
    from grading_allocation.constants import AllocationScope
    from grading_allocation.models import ProjectGraderAllocation
    from project_configuration.models import ProjectLabUnit

    scope_name = str(allocation_scope or "").strip()
    if scope_name not in {scope.value for scope in AllocationScope}:
        return _deny("project_allocation_target_required")
    if (
        scope_name
        in {
            AllocationScope.ENCOUNTER_SET_UNIFIED.value,
            AllocationScope.DISEASE_ENCOUNTER.value,
        }
        and encounter_set_type_id is None
    ):
        return _deny("encounter_set_type_required")
    allocation_disease_id = (
        None
        if scope_name == AllocationScope.ENCOUNTER_SET_UNIFIED.value
        else int(disease_id)
    )
    allocation_encounter_set_type_id = (
        None
        if scope_name == AllocationScope.DISEASE_IMAGE.value
        else int(encounter_set_type_id)
    )

    capacity = "arbitrator" if slot_name == "arbitrator" else "resident"
    allocation = context.db.execute(
        select(ProjectGraderAllocation.id)
        .where(
            ProjectGraderAllocation.project_id == record.project_id,
            ProjectGraderAllocation.user_id == context.user_id,
            ProjectGraderAllocation.lab_unit_id == record.lab_unit_id,
            ProjectGraderAllocation.capacity == capacity,
            ProjectGraderAllocation.active.is_(True),
            ProjectGraderAllocation.scope == scope_name,
            ProjectGraderAllocation.disease_id.is_not_distinct_from(
                allocation_disease_id
            ),
            ProjectGraderAllocation.encounter_set_type_id.is_not_distinct_from(
                allocation_encounter_set_type_id
            ),
            select(ProjectLabUnit.id)
            .where(
                ProjectLabUnit.project_id == record.project_id,
                ProjectLabUnit.lab_unit_id == record.lab_unit_id,
                ProjectLabUnit.active.is_(True),
            )
            .exists(),
        )
        .limit(1)
    ).scalar_one_or_none()
    if allocation is None:
        return _deny("project_grader_allocation_required")

    return _allow("project_grader_allocation")
