from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .errors import invalid

_LIST_FILTERS = frozenset(
    {
        "resident_grade",
        "resident2_grade",
        "arbitrator_grade",
        "review_grade",
        "final_grade",
        "regrade_grade",
        "ai_model_id",
        "ai_grade",
        "ai_review_status",
        "task_ids",
    }
)
_SCALAR_FILTERS = frozenset(
    {
        "project_id",
        "lab_unit_id",
        "has_ai_grade",
        "has_human_review",
        "has_review",
        "has_arbitrator",
        "has_regrade",
        "has_consensus",
        "consensus_method",
        "resident_compare",
        "final_grade_basis",
    }
)
_SCALAR_FILTER_VALUES = {
    "has_ai_grade": frozenset({"yes", "no"}),
    "has_human_review": frozenset({"unreviewed", "human", "ai", "both", "any"}),
    "has_review": frozenset({"yes", "no"}),
    "has_arbitrator": frozenset({"yes", "no"}),
    "has_regrade": frozenset({"yes", "no"}),
    "has_consensus": frozenset({"has_consensus", "no"}),
    "consensus_method": frozenset({"match", "adjudication", "task_review", "regrade"}),
    "resident_compare": frozenset({"match", "mismatch"}),
    "final_grade_basis": frozenset({"preference", "double_match"}),
}


def _required_positive_int(payload: Mapping[str, Any], name: str) -> int:
    value = payload.get(name)
    if isinstance(value, bool):
        raise invalid(f"{name} must be a positive integer.")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise invalid(f"{name} must be a positive integer.") from exc
    if parsed <= 0:
        raise invalid(f"{name} must be a positive integer.")
    return parsed


def _optional_positive_int(payload: Mapping[str, Any], name: str) -> int | None:
    value = payload.get(name)
    if value in (None, ""):
        return None
    return _required_positive_int(payload, name)


@dataclass(frozen=True)
class CreateRegradeTasksInput:
    disease_id: int
    assigned_to_user_id: int
    notes: str
    project_id: int | None = None
    lab_unit_id: int | None = None
    filters: dict[str, object] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> CreateRegradeTasksInput:
        if not isinstance(payload, Mapping):
            raise invalid("A JSON object is required.")
        notes = str(payload.get("notes") or payload.get("regrade_notes") or "").strip()
        if not notes:
            raise invalid("Regrade notes are required.")
        raw_filters = payload.get("filters") or {}
        if not isinstance(raw_filters, Mapping):
            raise invalid("filters must be an object.")
        filters: dict[str, object] = {}
        for name in _LIST_FILTERS:
            value = raw_filters.get(name, payload.get(name, []))
            if value in (None, ""):
                filters[name] = []
            elif isinstance(value, list):
                if name in {"ai_model_id", "task_ids"}:
                    parsed_values: list[int] = []
                    for item in value:
                        try:
                            parsed = int(item)
                        except (TypeError, ValueError) as exc:
                            raise invalid(f"filters.{name} must contain positive integers.") from exc
                        if parsed <= 0:
                            raise invalid(f"filters.{name} must contain positive integers.")
                        if parsed not in parsed_values:
                            parsed_values.append(parsed)
                    filters[name] = parsed_values
                else:
                    filters[name] = value
            else:
                raise invalid(f"filters.{name} must be an array.")
        for name in _SCALAR_FILTERS:
            if name in {"project_id", "lab_unit_id"}:
                continue
            value = raw_filters.get(name, payload.get(name))
            if value == "":
                value = None
            if value is not None and value not in _SCALAR_FILTER_VALUES[name]:
                raise invalid(f"filters.{name} contains an invalid value.")
            filters[name] = value
        return cls(
            disease_id=_required_positive_int(payload, "disease_id"),
            assigned_to_user_id=_required_positive_int(payload, "assigned_to_user_id"),
            notes=notes,
            project_id=_optional_positive_int(payload, "project_id"),
            lab_unit_id=_optional_positive_int(payload, "lab_unit_id"),
            filters=filters,
        )


@dataclass(frozen=True)
class SubmitRegradeInput:
    label_id: int
    comment: str | None = None
    selected_feature_ids: tuple[int, ...] = ()
    selected_features_supplied: bool = False
    feature_geometry_json: str | None = None
    feature_geometry_supplied: bool = False

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> SubmitRegradeInput:
        if not isinstance(payload, Mapping):
            raise invalid("A JSON object is required.")
        features_supplied = (
            "selected_feature_ids" in payload
            or "selected_features" in payload
            or payload.get("selected_features_present") == "1"
        )
        if not features_supplied:
            raise invalid("selected_feature_ids must be supplied, including when empty.")
        raw_ids = payload.get("selected_feature_ids", payload.get("selected_features", []))
        if raw_ids in (None, ""):
            raw_ids = []
        if not isinstance(raw_ids, list):
            raise invalid("selected_feature_ids must be an array.")
        feature_ids: list[int] = []
        for raw_id in raw_ids:
            try:
                feature_id = int(raw_id)
            except (TypeError, ValueError) as exc:
                raise invalid("Every selected feature ID must be an integer.") from exc
            if feature_id <= 0:
                raise invalid("Every selected feature ID must be positive.")
            if feature_id not in feature_ids:
                feature_ids.append(feature_id)
        geometry_supplied = "feature_geometry_json" in payload
        if not geometry_supplied:
            raise invalid("feature_geometry_json must be supplied, including when empty.")
        raw_geometry = payload.get("feature_geometry_json")
        if raw_geometry is not None and not isinstance(raw_geometry, str):
            raise invalid("feature_geometry_json must be a JSON string or null.")
        comment = str(payload.get("comment") or "").strip() or None
        return cls(
            label_id=_required_positive_int(payload, "label_id"),
            comment=comment,
            selected_feature_ids=tuple(feature_ids),
            selected_features_supplied=features_supplied,
            feature_geometry_json=raw_geometry,
            feature_geometry_supplied=geometry_supplied,
        )
