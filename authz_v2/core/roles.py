"""Canonical authorization roles and the scopes on which they may be granted."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class BreakGlassMode(StrEnum):
    NEVER = "never"
    ADMIN = "admin"


class ScopeType(StrEnum):
    SYSTEM = "system"
    HOSPITAL = "hospital"
    LAB_UNIT = "lab_unit"
    PROJECT = "project"
    PROJECT_LAB_UNIT = "project_lab_unit"


class Role(StrEnum):
    ADMIN = "admin"
    USER_MANAGER = "user_manager"
    LOCAL_ADMIN = "local_admin"
    DATA_MANAGER = "data_manager"
    FILE_UPLOADER = "fileUploader"
    PREGRADED_UPLOADER = "pregraded_uploader"
    OPHTHALMOLOGIST = "ophthalmologist"
    OPTOMETRIST = "optometrist"
    VERIFIER = "verifier"
    ANALYTICS_VIEWER = "analytics_viewer"
    DATASET_CREATOR = "dataset_creator"
    DATA_EXPORTER = "data_exporter"
    PII_EXPORTER = "pii_exporter"
    DISCREPANCY_REVIEWER = "discrepancy_reviewer"
    REGRADE_ADJUDICATOR = "regrade_adjudicator"
    PROJECT_PI = "project_pi"
    SITE_PI = "site_pi"
    PROJECT_ADMIN = "project_admin"
    COLLABORATOR = "collaborator"
    FIELD_OPTOMETRIST = "field_optometrist"
    FIELD_OPHTHALMOLOGIST = "field_ophthalmologist"


@dataclass(frozen=True)
class RoleContract:
    role: Role
    label: str
    purpose: str
    permitted_scope_types: frozenset[ScopeType]
    delegable_by: frozenset[Role] = frozenset()


SYSTEM = frozenset({ScopeType.SYSTEM})
HOSPITAL = frozenset({ScopeType.HOSPITAL})
CLASSICAL = frozenset({ScopeType.HOSPITAL, ScopeType.LAB_UNIT})
PROJECT = frozenset({ScopeType.PROJECT, ScopeType.PROJECT_LAB_UNIT})
OPERATIONAL = CLASSICAL | PROJECT
SYSTEM_DELEGATOR = frozenset({Role.ADMIN})
OPERATIONAL_DELEGATORS = frozenset({Role.ADMIN, Role.LOCAL_ADMIN, Role.PROJECT_ADMIN})
PROJECT_DELEGATORS = frozenset({Role.ADMIN, Role.PROJECT_ADMIN})
PROJECT_ADMIN_DELEGATORS = frozenset({Role.ADMIN, Role.PROJECT_PI, Role.SITE_PI})


def _contract(
    role: Role,
    purpose: str,
    scopes: frozenset[ScopeType],
    *,
    delegable_by: frozenset[Role] = frozenset(),
) -> RoleContract:
    return RoleContract(
        role, role.value.replace("_", " ").title(), purpose, scopes, delegable_by
    )


ROLE_CONTRACTS: dict[Role, RoleContract] = {
    Role.ADMIN: _contract(Role.ADMIN, "System administration and break-glass", SYSTEM),
    Role.USER_MANAGER: _contract(
        Role.USER_MANAGER,
        "User administration within a hospital",
        HOSPITAL,
        delegable_by=frozenset({Role.ADMIN}),
    ),
    Role.LOCAL_ADMIN: _contract(
        Role.LOCAL_ADMIN,
        "Hospital operations without user-delegation authority",
        HOSPITAL,
        delegable_by=SYSTEM_DELEGATOR,
    ),
    Role.DATA_MANAGER: _contract(
        Role.DATA_MANAGER,
        "Scoped data operations",
        OPERATIONAL,
        delegable_by=OPERATIONAL_DELEGATORS,
    ),
    Role.FILE_UPLOADER: _contract(
        Role.FILE_UPLOADER,
        "Scoped upload operations",
        OPERATIONAL,
        delegable_by=OPERATIONAL_DELEGATORS,
    ),
    Role.PREGRADED_UPLOADER: _contract(
        Role.PREGRADED_UPLOADER,
        "Scoped pregraded uploads",
        OPERATIONAL,
        delegable_by=OPERATIONAL_DELEGATORS,
    ),
    Role.OPHTHALMOLOGIST: _contract(
        Role.OPHTHALMOLOGIST,
        "Clinical grading qualification",
        OPERATIONAL,
        delegable_by=OPERATIONAL_DELEGATORS,
    ),
    Role.OPTOMETRIST: _contract(
        Role.OPTOMETRIST,
        "Clinical capture and upload operations",
        OPERATIONAL,
        delegable_by=OPERATIONAL_DELEGATORS,
    ),
    Role.VERIFIER: _contract(
        Role.VERIFIER,
        "Encounter and image verification",
        OPERATIONAL,
        delegable_by=OPERATIONAL_DELEGATORS,
    ),
    Role.ANALYTICS_VIEWER: _contract(
        Role.ANALYTICS_VIEWER,
        "Scoped masked analytics",
        OPERATIONAL,
        delegable_by=OPERATIONAL_DELEGATORS,
    ),
    Role.DATASET_CREATOR: _contract(
        Role.DATASET_CREATOR,
        "Dataset assembly and curation",
        OPERATIONAL,
        delegable_by=OPERATIONAL_DELEGATORS,
    ),
    Role.DATA_EXPORTER: _contract(
        Role.DATA_EXPORTER,
        "Dataset and review export",
        OPERATIONAL,
        delegable_by=OPERATIONAL_DELEGATORS,
    ),
    Role.PII_EXPORTER: _contract(
        Role.PII_EXPORTER,
        "Additive authority to release identifiers",
        OPERATIONAL,
        delegable_by=SYSTEM_DELEGATOR,
    ),
    Role.DISCREPANCY_REVIEWER: _contract(
        Role.DISCREPANCY_REVIEWER,
        "Scoped discrepancy review",
        OPERATIONAL,
        delegable_by=OPERATIONAL_DELEGATORS,
    ),
    Role.REGRADE_ADJUDICATOR: _contract(
        Role.REGRADE_ADJUDICATOR,
        "Scoped regrade adjudication",
        OPERATIONAL,
        delegable_by=OPERATIONAL_DELEGATORS,
    ),
    Role.PROJECT_PI: _contract(
        Role.PROJECT_PI,
        "Project-wide scientific oversight",
        frozenset({ScopeType.PROJECT}),
        delegable_by=SYSTEM_DELEGATOR,
    ),
    Role.SITE_PI: _contract(
        Role.SITE_PI,
        "Project-site scientific oversight",
        frozenset({ScopeType.PROJECT_LAB_UNIT}),
        delegable_by=SYSTEM_DELEGATOR,
    ),
    Role.PROJECT_ADMIN: _contract(
        Role.PROJECT_ADMIN,
        "Project or project-site access administration",
        PROJECT,
        delegable_by=PROJECT_ADMIN_DELEGATORS,
    ),
    Role.COLLABORATOR: _contract(
        Role.COLLABORATOR,
        "Scoped masked project collaboration",
        PROJECT,
        delegable_by=PROJECT_DELEGATORS,
    ),
    Role.FIELD_OPTOMETRIST: _contract(
        Role.FIELD_OPTOMETRIST,
        "Project field capture as optometrist",
        PROJECT,
        delegable_by=PROJECT_DELEGATORS,
    ),
    Role.FIELD_OPHTHALMOLOGIST: _contract(
        Role.FIELD_OPHTHALMOLOGIST,
        "Project field capture as ophthalmologist",
        PROJECT,
        delegable_by=PROJECT_DELEGATORS,
    ),
}


def canonical_role(value: Role | str) -> Role:
    return value if isinstance(value, Role) else Role(value)


def role_accepts_scope(role: Role, scope_type: ScopeType) -> bool:
    return scope_type in ROLE_CONTRACTS[role].permitted_scope_types


def may_delegate(delegator: Role, role: Role) -> bool:
    return delegator in ROLE_CONTRACTS[role].delegable_by
