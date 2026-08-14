"""Transport-neutral value objects shared by authorization policy adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class GrantSource(StrEnum):
    """Relationship sources accepted by central authorization policies."""

    UPLOAD_PROFILE = "upload_profile"
    GRADING_SLOT = "grading_slot"
    LAB_UNIT_ASSIGNMENT = "lab_unit_assignment"
    HOSPITAL_SCOPE = "hospital_scope"
    ADMIN_GLOBAL = "admin_global"
    PROJECT_ROLE = "project_role"
    LEGACY_PROJECT_CAPABILITY = "legacy_project_capability"
    PROJECT_COLLABORATOR = "project_collaborator"
    TASK_ELIGIBILITY = "task_eligibility"
    MEDIA_UPLOADER = "media_uploader"
    SIGNED_MEDIA_TOKEN = "signed_media_token"


@dataclass(frozen=True)
class AuthzActor:
    """Detached actor context used by authz policy checks."""

    id: int
    roles: frozenset[str] = field(default_factory=frozenset)
    hospital_id: int | None = None

    def has_any_role(self, roles: frozenset[str]) -> bool:
        """Return whether actor roles intersect a policy role set, case-insensitively."""
        actor_roles = {role.lower() for role in self.roles}
        return bool(actor_roles.intersection({role.lower() for role in roles}))


@dataclass(frozen=True)
class ResourceRef:
    """Small, route/service-safe reference to the resource being authorized."""

    type: str
    id: int | str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)

    def attr(self, name: str) -> Any:
        """Read one optional normalized resource attribute."""
        return self.attributes.get(name)


@dataclass(frozen=True)
class RelationshipGrant:
    """Resolved relationship between an actor and a resource family."""

    source: GrantSource
    hospital_id: int | None = None
    lab_unit_id: int | None = None
    resource_id: int | str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)

    def attr(self, name: str) -> Any:
        """Read one optional relationship attribute."""
        return self.attributes.get(name)


@dataclass(frozen=True)
class AuthzDecision:
    """Allow/deny result with enough evidence for tests, logs, and audits."""

    allowed: bool
    action: str
    reason: str
    grant_source: GrantSource | None = None

    @classmethod
    def allow(cls, action: str, grant_source: GrantSource) -> "AuthzDecision":
        """Construct a successful decision with its supporting relationship."""
        return cls(True, action, "allowed", grant_source)

    @classmethod
    def deny(cls, action: str, reason: str) -> "AuthzDecision":
        """Construct a denied decision for internal evaluation and tests."""
        return cls(False, action, reason)
