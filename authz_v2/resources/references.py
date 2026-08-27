"""Strict transport-reference validation for exact authorization targets."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AutomationTargetRef:
    """Exact domain target paired with the stored rule that triggered it."""

    target: object
    automation_rule_id: int


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
