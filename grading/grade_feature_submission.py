"""Shared grade feature and annotation submission handling."""
from __future__ import annotations

from dataclasses import dataclass
import json
from json import JSONDecodeError

from models import DiseaseGrading, Grade, GradingTask, GradingsFeatures, ImageMetadata
from project_annotations.service import (
    resolve_task_annotation_context,
    validate_geometry_policy,
)
from utils.feature_geometry import (
    parse_feature_geometry_payload,
    prepare_feature_geometry_for_storage,
    validate_feature_geometry_payload,
)


class GradeFeatureValidationError(ValueError):
    """Raised when submitted features or geometry do not match the grade/task."""


@dataclass(frozen=True)
class GradeFeatureSubmissionDTO:
    selected_features_json: str | None
    feature_geometry_json: dict | None


def parse_selected_features(value: str | None) -> list[dict[str, object] | str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def serialize_grade_features(labels: list[DiseaseGrading]) -> list[dict[str, object]]:
    return [
        {
            "id": label.id,
            "impression": label.impression,
            "display_order": label.display_order,
            "is_ungradable": bool(label.is_ungradable),
            "features": [
                {
                    "id": feature.id,
                    "sr_no": feature.sr_no,
                    "label": feature.label,
                }
                for feature in sorted(
                    label.features or [],
                    key=lambda item: ((item.sr_no or 0), item.id),
                )
            ],
        }
        for label in labels
    ]


def prepare_grade_feature_submission(
    db,
    *,
    task: GradingTask,
    label_id: int,
    raw_selected_features: list[str],
    raw_feature_geometry: str | None,
    existing_grade: Grade | None,
) -> GradeFeatureSubmissionDTO:
    feature_ids = _parse_feature_ids(raw_selected_features)
    features = _validated_features(db, label_id=label_id, feature_ids=feature_ids)
    selected_features_json = (
        json.dumps(
            [
                {"id": feature.id, "label": feature.label, "sr_no": feature.sr_no}
                for feature in features
            ]
        )
        if features
        else None
    )

    if raw_feature_geometry is None:
        geometry = existing_grade.feature_geometry_json if existing_grade else None
    elif not raw_feature_geometry.strip():
        geometry = None
    else:
        parsed_geometry = parse_feature_geometry_payload(raw_feature_geometry)
        if parsed_geometry is None:
            raise GradeFeatureValidationError("Invalid feature geometry submitted.")
        image_metadata = _fetch_image_metadata(db, task)
        is_valid, error = validate_feature_geometry_payload(
            parsed_geometry,
            feature_ids,
            image_metadata,
        )
        if not is_valid:
            raise GradeFeatureValidationError(error or "Invalid feature geometry submitted.")
        annotation_context = resolve_task_annotation_context(db, task)
        is_policy_valid, policy_error = validate_geometry_policy(
            parsed_geometry,
            annotation_context,
        )
        if not is_policy_valid:
            raise GradeFeatureValidationError(
                policy_error or "The annotation does not match the project policy."
            )
        geometry = prepare_feature_geometry_for_storage(
            parsed_geometry,
            image_metadata,
            feature_metadata_by_id={
                int(feature.id): {"label": feature.label, "sr_no": feature.sr_no}
                for feature in features
            },
            annotation_context=annotation_context.to_dict(),
        )

    return GradeFeatureSubmissionDTO(
        selected_features_json=selected_features_json,
        feature_geometry_json=geometry,
    )


def _parse_feature_ids(raw_values: list[str]) -> list[int]:
    feature_ids: list[int] = []
    seen: set[int] = set()
    for raw_value in raw_values:
        if raw_value in {None, ""}:
            continue
        try:
            feature_id = int(raw_value)
        except (TypeError, ValueError) as exc:
            raise GradeFeatureValidationError("Invalid feature selection submitted.") from exc
        if feature_id not in seen:
            feature_ids.append(feature_id)
            seen.add(feature_id)
    return feature_ids


def _validated_features(db, *, label_id: int, feature_ids: list[int]) -> list[GradingsFeatures]:
    if not feature_ids:
        return []
    available = (
        db.query(GradingsFeatures)
        .filter(GradingsFeatures.disease_grading_id == label_id)
        .all()
    )
    by_id = {feature.id: feature for feature in available}
    if any(feature_id not in by_id for feature_id in feature_ids):
        raise GradeFeatureValidationError(
            "One or more selected features are not valid for the chosen grade."
        )
    return sorted(
        (by_id[feature_id] for feature_id in feature_ids),
        key=lambda item: ((item.sr_no or 0), item.id),
    )


def _fetch_image_metadata(db, task: GradingTask) -> ImageMetadata | None:
    image = task.encounter_set_image
    if image is None:
        return None
    return (
        db.query(ImageMetadata)
        .filter(
            ImageMetadata.image_uuid == image.uuid,
            ImageMetadata.image_variant == "orig",
        )
        .first()
    )
