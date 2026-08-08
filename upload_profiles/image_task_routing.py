"""Image-level task routing rules for EncounterSet upload profiles."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def image_metadata_matches_rule(
    metadata: Mapping[str, Any] | None,
    rule: Mapping[str, Any] | None,
) -> bool:
    """Return whether normalized image metadata satisfies an optional equality rule."""
    if not rule:
        return True
    field_key = str(rule.get("field_key") or "").strip()
    expected = str(rule.get("match_value") or "").strip()
    if not field_key or not expected:
        return False
    actual = (metadata or {}).get(field_key)
    if isinstance(actual, list):
        return any(_scalar_matches(value, expected) for value in actual)
    return _scalar_matches(actual, expected)


def _scalar_matches(actual: Any, expected: str) -> bool:
    if actual is None or isinstance(actual, (dict, list)):
        return False
    if isinstance(actual, bool):
        return expected.lower() == ("true" if actual else "false")
    return str(actual).strip() == expected
