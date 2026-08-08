"""Image-level task routing rules for EncounterSet upload profiles."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ImageTaskRoutingField:
    """Image metadata field required to route an eligible grading task."""

    key: str
    label: str


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


def required_image_task_routing_fields(profile_config: Any | None) -> tuple[ImageTaskRoutingField, ...]:
    """Return metadata fields used by active image task auto-creation rules."""
    if profile_config is None:
        return ()

    field_labels = _image_field_labels(profile_config)
    required: dict[str, ImageTaskRoutingField] = {}
    for package in getattr(profile_config, "grading_packages", ()) or ():
        if not getattr(package, "active", False):
            continue
        if getattr(package, "applicability", "always") in {"disabled", "manual_only"}:
            continue
        for scheme in getattr(package, "image_grading_schemes", ()) or ():
            if not getattr(scheme, "active", False):
                continue
            if getattr(scheme, "auto_create_policy", "always") == "never":
                continue
            field_key = str(getattr(scheme, "metadata_field_key", "") or "").strip()
            match_value = str(getattr(scheme, "metadata_match_value", "") or "").strip()
            if not field_key or not match_value:
                continue
            required[field_key] = ImageTaskRoutingField(
                key=field_key,
                label=field_labels.get(field_key, field_key.replace("_", " ").title()),
            )
    return tuple(required[key] for key in sorted(required))


def missing_image_task_routing_fields(
    image: Any,
    profile_config: Any | None,
) -> tuple[ImageTaskRoutingField, ...]:
    """Return routing fields missing from one gradable, task-eligible image."""
    if not image_is_eligible_for_routing_validation(image):
        return ()
    metadata = getattr(image, "metadata_json", None)
    metadata = metadata if isinstance(metadata, Mapping) else {}
    return tuple(
        field
        for field in required_image_task_routing_fields(profile_config)
        if not _metadata_value_is_present(metadata.get(field.key))
    )


def image_is_eligible_for_routing_validation(image: Any) -> bool:
    """Return whether an image can produce a grading task after verification."""
    return bool(
        getattr(image, "asset_kind", None) == "clinical_image"
        and getattr(image, "creates_task", False)
        and getattr(image, "visible_to_grader", False)
        and not getattr(image, "is_not_gradable", False)
    )


def _image_field_labels(profile_config: Any) -> dict[str, str]:
    encounter_set_type = getattr(profile_config, "encounter_set_type", None)
    schema = getattr(encounter_set_type, "metadata_schema_json", None)
    fields = schema.get("fields", []) if isinstance(schema, Mapping) else []
    return {
        str(field["key"]): str(field.get("label") or field["key"])
        for field in fields
        if isinstance(field, Mapping) and field.get("scope") == "image" and field.get("key")
    }


def _metadata_value_is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _scalar_matches(actual: Any, expected: str) -> bool:
    if actual is None or isinstance(actual, (dict, list)):
        return False
    if isinstance(actual, bool):
        return expected.lower() == ("true" if actual else "false")
    return str(actual).strip() == expected
