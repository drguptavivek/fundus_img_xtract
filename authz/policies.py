from __future__ import annotations

from dataclasses import dataclass

from authz.types import GrantSource


@dataclass(frozen=True)
class ActionPolicy:
    """Policy contract for one explicit application action."""

    roles: frozenset[str]
    grant_sources: frozenset[GrantSource]


GENERAL_SCOPE_GRANTS = frozenset(
    {
        GrantSource.ADMIN_GLOBAL,
        GrantSource.HOSPITAL_SCOPE,
        GrantSource.LAB_UNIT_ASSIGNMENT,
    }
)

VERIFICATION_ROLES = frozenset({"admin", "local_admin", "fileUploader", "optometrist", "data_manager"})

POLICIES: dict[str, ActionPolicy] = {
    "upload.direct.create": ActionPolicy(
        roles=frozenset({"fileUploader"}),
        grant_sources=frozenset({GrantSource.UPLOAD_PROFILE}),
    ),
    "grading.resident.submit": ActionPolicy(
        roles=frozenset({"resident", "ophthalmologist"}),
        grant_sources=frozenset({GrantSource.GRADING_SLOT}),
    ),
    "analytics.encounters.view": ActionPolicy(
        roles=frozenset({"admin", "local_admin", "data_manager", "analytics_viewer", "ophthalmologist"}),
        grant_sources=GENERAL_SCOPE_GRANTS,
    ),
    "verification.direct.view": ActionPolicy(
        roles=VERIFICATION_ROLES,
        grant_sources=GENERAL_SCOPE_GRANTS,
    ),
    "verification.direct.update": ActionPolicy(
        roles=VERIFICATION_ROLES,
        grant_sources=GENERAL_SCOPE_GRANTS,
    ),
    "verification.remidio.view": ActionPolicy(
        roles=VERIFICATION_ROLES,
        grant_sources=GENERAL_SCOPE_GRANTS,
    ),
    "verification.remidio.update": ActionPolicy(
        roles=VERIFICATION_ROLES,
        grant_sources=GENERAL_SCOPE_GRANTS,
    ),
    "verification.pregraded.view": ActionPolicy(
        roles=VERIFICATION_ROLES,
        grant_sources=GENERAL_SCOPE_GRANTS,
    ),
    "verification.pregraded.update": ActionPolicy(
        roles=VERIFICATION_ROLES,
        grant_sources=GENERAL_SCOPE_GRANTS,
    ),
}


def get_policy(action: str) -> ActionPolicy | None:
    return POLICIES.get(action)
