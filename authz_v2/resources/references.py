"""Strict transport-reference validation for exact authorization targets."""

from __future__ import annotations

from dataclasses import dataclass

from authz_v2.core.resources import ScopeDTO
from authz_v2.core.roles import Role


@dataclass(frozen=True)
class AutomationTargetRef:
    """Exact domain target paired with the stored rule that triggered it."""

    target: object
    automation_rule_id: int


@dataclass(frozen=True)
class UserCreationTargetRef:
    """Requested account scope and grants, supplied together or denied."""

    hospital_id: int
    requested_grants: tuple[tuple[Role, ScopeDTO], ...]


@dataclass(frozen=True)
class AdminMobileSessionTargetRef:
    """Bind an admin session mutation to both URL identifiers."""

    user_id: int
    session_id: str


@dataclass(frozen=True)
class SystemOperationRef:
    """Closed identifier for an exact system-maintenance mutation."""

    operation: str


@dataclass(frozen=True)
class ActiveConfigurationRef:
    """Resolve the single active configuration of a declared kind."""

    kind: str


@dataclass(frozen=True)
class LookupRecordRef:
    """Typed lookup identity; bare integers are intentionally ambiguous."""

    kind: str
    record_id: int


def is_positive_int(value: object) -> bool:
    """Accept database identifiers, never booleans, zero, or negative values."""
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def is_stable_resource_id(value: object) -> bool:
    """Accept a positive integer or a non-empty bounded opaque identifier."""
    if is_positive_int(value):
        return True
    return (
        isinstance(value, str)
        and value == value.strip()
        and 0 < len(value) <= 255
        and not any(character.isspace() for character in value)
    )
