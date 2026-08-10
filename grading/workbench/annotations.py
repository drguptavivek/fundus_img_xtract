"""Common grading-feature and normalized annotation observation pipeline."""

from __future__ import annotations

import json
import base64
import hashlib
import struct
from uuid import UUID

from models import DiseaseGrading, Grade, GradingTask, GradingsFeatures, ImageMetadata
from project_annotations.models import ProjectAnnotationClass
from project_annotations.service import resolve_task_annotation_context, validate_geometry_policy
from utils.feature_geometry import (
    parse_feature_geometry_payload,
    prepare_feature_geometry_for_storage,
    validate_feature_geometry_payload,
)

from .contracts import AnnotationInstanceInputDTO, GradeObservationDTO
from .errors import AnnotationPolicyChanged, AnnotationValidationError
from .models import AnnotationInstance, AnnotationMaskTile, AnnotationSet
from .sources import resolve_task_source


def parse_grade_observation(
    db,
    *,
    task: GradingTask,
    label_id: int,
    comment: str | None,
    raw_selected_features: list[str],
    raw_feature_geometry: str | None,
    submitted_policy_revision: int | str | None,
    existing_grade: Grade | None,
) -> GradeObservationDTO:
    label = (
        db.query(DiseaseGrading)
        .filter(DiseaseGrading.id == label_id, DiseaseGrading.disease_id == task.disease_id)
        .first()
    )
    if label is None:
        raise AnnotationValidationError("The selected grade is not valid for this task.")

    feature_ids = _parse_feature_ids(raw_selected_features)
    features = _validated_features(db, label_id=label_id, feature_ids=feature_ids)
    selected_features_json = (
        json.dumps(
            [{"id": item.id, "label": item.label, "sr_no": item.sr_no} for item in features],
            separators=(",", ":"),
            sort_keys=True,
        )
        if features
        else None
    )

    context = resolve_task_annotation_context(db, task)
    try:
        submitted_revision = int(submitted_policy_revision) if submitted_policy_revision is not None else None
    except (TypeError, ValueError) as exc:
        raise AnnotationPolicyChanged("The annotation policy revision is invalid. Reload before submitting.") from exc
    if submitted_revision != context.revision:
        raise AnnotationPolicyChanged("The project annotation policy changed. Reload before submitting.")

    explicit_clear = raw_feature_geometry is not None and not raw_feature_geometry.strip()
    if raw_feature_geometry is None:
        geometry = existing_grade.feature_geometry_json if existing_grade else None
    elif explicit_clear:
        geometry = None
    else:
        geometry = _parse_and_normalize_geometry(
            db,
            task=task,
            raw=raw_feature_geometry,
            feature_ids=feature_ids,
            features=features,
            annotation_context=context,
        )

    # Validate the policy even for empty or explicitly-cleared geometry. The
    # legacy policy helper intentionally treats empty items as valid, while the
    # explicit revision check above still prevents stale clears.
    valid, error = validate_geometry_policy(geometry, context)
    if not valid:
        raise AnnotationValidationError(error or "The annotation does not match the project policy.")

    source = resolve_task_source(db, task)
    instances = _instances_from_geometry(
        geometry,
        image_uuid=source.media.image_uuid if source.media else None,
    )
    if instances and source.media is None:
        raise AnnotationValidationError("Encounter-level targets cannot contain image geometry.")

    return GradeObservationDTO(
        task_uuid=task.uuid,
        disease_grading_id=label.id,
        comment=(comment or "").strip() or None,
        selected_feature_ids=tuple(feature_ids),
        selected_features_json=selected_features_json,
        feature_geometry_json=geometry,
        annotation_policy_revision=context.revision,
        annotation_instances=instances,
        explicit_geometry_clear=explicit_clear,
    )


def persist_grade_annotations(db, *, grade: Grade, task: GradingTask, observation: GradeObservationDTO) -> AnnotationSet:
    """Replace a grade's normalized annotations in the surrounding transaction."""
    source = resolve_task_source(db, task)
    annotation_set = db.query(AnnotationSet).filter(AnnotationSet.grade_id == grade.id).first()
    if annotation_set is None:
        annotation_set = AnnotationSet(
            grade_id=grade.id,
            policy_source=resolve_task_annotation_context(db, task).policy_source,
            policy_revision=observation.annotation_policy_revision,
        )
        db.add(annotation_set)
        db.flush()
    annotation_set.policy_revision = observation.annotation_policy_revision
    annotation_set.source_image_width = source.media.width if source.media else None
    annotation_set.source_image_height = source.media.height if source.media else None
    annotation_set.instances.clear()

    for order, submitted in enumerate(observation.annotation_instances):
        identity = _class_identity(db, submitted)
        bbox = _bbox(submitted.geometry)
        instance = AnnotationInstance(
            image_uuid=submitted.image_uuid,
            class_source=submitted.class_source,
            grading_feature_id=submitted.grading_feature_id,
            project_class_id=submitted.project_class_id,
            class_key_snapshot=identity[0],
            class_label_snapshot=identity[1],
            policy_revision=observation.annotation_policy_revision,
            geometry_type=submitted.geometry_type,
            geometry_json=submitted.geometry,
            bbox_x=bbox[0],
            bbox_y=bbox[1],
            bbox_w=bbox[2],
            bbox_h=bbox[3],
            instance_order=order,
        )
        if submitted.instance_uuid:
            instance.uuid = submitted.instance_uuid
        annotation_set.instances.append(instance)
        for tile in submitted.mask_tiles:
            instance.mask_tiles.append(AnnotationMaskTile(**_decoded_mask_tile(tile)))
    db.flush()
    return annotation_set


def _parse_and_normalize_geometry(db, *, task, raw, feature_ids, features, annotation_context):
    parsed = parse_feature_geometry_payload(raw)
    if parsed is None:
        raise AnnotationValidationError("Invalid annotation geometry submitted.")
    metadata = _image_metadata(db, task)
    valid, error = validate_feature_geometry_payload(parsed, feature_ids, metadata)
    if not valid:
        raise AnnotationValidationError(error or "Invalid annotation geometry submitted.")
    valid, error = validate_geometry_policy(parsed, annotation_context)
    if not valid:
        if "policy changed" in (error or "").lower():
            raise AnnotationPolicyChanged(error)
        raise AnnotationValidationError(error or "The annotation does not match the project policy.")
    return prepare_feature_geometry_for_storage(
        parsed,
        metadata,
        feature_metadata_by_id={item.id: {"label": item.label, "sr_no": item.sr_no} for item in features},
        annotation_context=annotation_context.to_dict(),
    )


def _parse_feature_ids(values: list[str]) -> list[int]:
    result: list[int] = []
    for raw in values:
        if raw in (None, ""):
            continue
        try:
            value = int(raw)
        except (TypeError, ValueError) as exc:
            raise AnnotationValidationError("Invalid feature selection submitted.") from exc
        if value not in result:
            result.append(value)
    return result


def _validated_features(db, *, label_id: int, feature_ids: list[int]) -> list[GradingsFeatures]:
    available = (
        db.query(GradingsFeatures)
        .filter(GradingsFeatures.disease_grading_id == label_id)
        .all()
    )
    by_id = {item.id: item for item in available}
    if any(item not in by_id for item in feature_ids):
        raise AnnotationValidationError("A selected feature does not belong to the chosen grade.")
    return sorted((by_id[item] for item in feature_ids), key=lambda item: (item.sr_no, item.id))


def _image_metadata(db, task: GradingTask) -> ImageMetadata | None:
    source = resolve_task_source(db, task)
    if source.media is None:
        return None
    return (
        db.query(ImageMetadata)
        .filter(ImageMetadata.image_uuid == source.media.image_uuid, ImageMetadata.image_variant == "orig")
        .first()
    )


def _instances_from_geometry(geometry: dict | None, *, image_uuid: str | None) -> tuple[AnnotationInstanceInputDTO, ...]:
    if not geometry:
        return ()
    items = geometry.get("items")
    if not isinstance(items, list):
        return ()
    result: list[AnnotationInstanceInputDTO] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        instance_uuid = item.get("instance_uuid")
        if instance_uuid:
            try:
                instance_uuid = str(UUID(str(instance_uuid)))
            except ValueError as exc:
                raise AnnotationValidationError("Invalid annotation instance identity.") from exc
        source = item.get("class_source", "grading_feature")
        geometry_type = str(item.get("geometry_type") or "box")
        mask_tiles = _validated_mask_tiles(item.get("mask_tiles"))
        if mask_tiles and geometry_type != "brush_mask":
            raise AnnotationValidationError("Mask tiles require brush-mask geometry.")
        result.append(
            AnnotationInstanceInputDTO(
                instance_uuid=instance_uuid,
                image_uuid=image_uuid or "",
                class_source=source,
                grading_feature_id=item.get("feature_id") if source == "grading_feature" else None,
                project_class_id=item.get("project_class_id") if source == "project_class" else None,
                project_class_key=item.get("project_class_key") if source == "project_class" else None,
                geometry_type=geometry_type,
                geometry=item,
                mask_tiles=mask_tiles,
            )
        )
    return tuple(result)


def _validated_mask_tiles(value) -> tuple[dict, ...]:
    if value in (None, []):
        return ()
    if not isinstance(value, list) or len(value) > 1024:
        raise AnnotationValidationError("Invalid segmentation mask tiles.")
    result = []
    positions = set()
    total_bytes = 0
    for raw in value:
        if not isinstance(raw, dict):
            raise AnnotationValidationError("Invalid segmentation mask tile.")
        try:
            tile_x = int(raw["tile_x"])
            tile_y = int(raw["tile_y"])
            width = int(raw["width"])
            height = int(raw["height"])
            encoded = str(raw["png_base64"])
            png_bytes = base64.b64decode(encoded, validate=True)
        except (KeyError, TypeError, ValueError) as exc:
            raise AnnotationValidationError("Invalid segmentation mask tile.") from exc
        if tile_x < 0 or tile_y < 0 or not (1 <= width <= 256 and 1 <= height <= 256):
            raise AnnotationValidationError("Invalid segmentation mask tile dimensions.")
        if (tile_x, tile_y) in positions:
            raise AnnotationValidationError("Duplicate segmentation mask tile position.")
        positions.add((tile_x, tile_y))
        if len(png_bytes) > 1024 * 1024:
            raise AnnotationValidationError("A segmentation mask tile is too large.")
        total_bytes += len(png_bytes)
        if total_bytes > 16 * 1024 * 1024:
            raise AnnotationValidationError("The segmentation mask is too large.")
        png_width, png_height = _png_dimensions(png_bytes)
        if (png_width, png_height) != (width, height):
            raise AnnotationValidationError("Segmentation mask tile dimensions do not match its PNG.")
        checksum = hashlib.sha256(png_bytes).hexdigest()
        supplied_checksum = raw.get("checksum")
        if supplied_checksum and supplied_checksum != checksum:
            raise AnnotationValidationError("Segmentation mask tile checksum mismatch.")
        result.append({
            "tile_x": tile_x,
            "tile_y": tile_y,
            "width": width,
            "height": height,
            "png_base64": encoded,
            "checksum": checksum,
        })
    return tuple(result)


def _decoded_mask_tile(tile: dict) -> dict:
    return {
        "tile_x": tile["tile_x"],
        "tile_y": tile["tile_y"],
        "width": tile["width"],
        "height": tile["height"],
        "png_bytes": base64.b64decode(tile["png_base64"], validate=True),
        "checksum": tile["checksum"],
    }


def _png_dimensions(payload: bytes) -> tuple[int, int]:
    if len(payload) < 24 or payload[:8] != b"\x89PNG\r\n\x1a\n" or payload[12:16] != b"IHDR":
        raise AnnotationValidationError("Segmentation mask tile must be a PNG image.")
    return struct.unpack(">II", payload[16:24])


def _class_identity(db, item: AnnotationInstanceInputDTO) -> tuple[str, str]:
    if item.class_source == "grading_feature":
        feature = db.get(GradingsFeatures, item.grading_feature_id)
        if feature is None:
            raise AnnotationValidationError("An annotation feature is unavailable.")
        return f"grading_feature:{feature.id}", feature.label
    project_class = db.get(ProjectAnnotationClass, item.project_class_id)
    if project_class is None or project_class.key != item.project_class_key:
        raise AnnotationValidationError("A project annotation class identity is stale.")
    return project_class.key, project_class.key


def _bbox(geometry: dict) -> tuple[float | None, float | None, float | None, float | None]:
    export = geometry.get("export") if isinstance(geometry.get("export"), dict) else {}
    xyxy = export.get("bbox_pixel_xyxy")
    if isinstance(xyxy, list) and len(xyxy) == 4:
        x1, y1, x2, y2 = (float(value) for value in xyxy)
        return x1, y1, max(0.0, x2 - x1), max(0.0, y2 - y1)
    roi = geometry.get("roi") if isinstance(geometry.get("roi"), dict) else {}
    points = roi.get("pixel")
    if isinstance(points, list) and len(points) == 2:
        x_values = [float(point[0]) for point in points]
        y_values = [float(point[1]) for point in points]
        return min(x_values), min(y_values), abs(x_values[1] - x_values[0]), abs(y_values[1] - y_values[0])
    return None, None, None, None
