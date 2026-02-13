import json
import logging
from typing import Any, Iterable

from models import ImageMetadata

logger = logging.getLogger("feature_geometry")

ALLOWED_GEOMETRY_TYPES = {"point", "polygon", "line", "polyline", "box"}


def parse_feature_geometry_payload(raw: str | None) -> dict | None:
    if raw is None:
        return None
    raw = raw.strip()
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Failed to decode feature geometry payload", exc_info=True)
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def validate_feature_geometry_payload(
    payload: dict | None,
    selected_feature_ids: Iterable[int] | None,
    image_metadata: ImageMetadata | None,
) -> tuple[bool, str]:
    if payload is None:
        return True, ""

    items = payload.get("items")
    if not isinstance(items, list):
        return False, "Invalid feature geometry payload."

    allowed_features = set(selected_feature_ids or [])
    width = image_metadata.width if image_metadata else None
    height = image_metadata.height if image_metadata else None

    for item in items:
        if not isinstance(item, dict):
            return False, "Invalid feature geometry payload."

        feature_id = item.get("feature_id")
        if not isinstance(feature_id, int):
            return False, "Invalid feature geometry payload."
        if allowed_features and feature_id not in allowed_features:
            return False, "Feature geometry does not match selected features."

        geom = item.get("geom")
        if not isinstance(geom, dict):
            return False, "Invalid feature geometry payload."

        geom_type = geom.get("type")
        if geom_type not in ALLOWED_GEOMETRY_TYPES:
            return False, "Invalid geometry type submitted."

        pixel_points = geom.get("pixel")
        norm_points = geom.get("norm")
        if not (_is_point_list(pixel_points) and _is_point_list(norm_points)):
            return False, "Invalid geometry coordinates submitted."

        if width is not None and height is not None:
            if not _points_within_bounds(pixel_points, width, height):
                return False, "Geometry coordinates are outside image bounds."

        if not _points_within_unit_square(norm_points):
            return False, "Normalized geometry coordinates are out of range."

    return True, ""


def _is_point_list(value: Any) -> bool:
    if not isinstance(value, list) or not value:
        return False
    for point in value:
        if not _is_point(point):
            return False
    return True


def _is_point(value: Any) -> bool:
    if (
        not isinstance(value, (list, tuple))
        or len(value) != 2
        or not _is_number(value[0])
        or not _is_number(value[1])
    ):
        return False
    return True


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float))


def _points_within_bounds(points: list, width: int, height: int) -> bool:
    for x, y in points:
        if x < 0 or y < 0 or x > width or y > height:
            return False
    return True


def _points_within_unit_square(points: list) -> bool:
    for x, y in points:
        if x < 0 or y < 0 or x > 1 or y > 1:
            return False
    return True
