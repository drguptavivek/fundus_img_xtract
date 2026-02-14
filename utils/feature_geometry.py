import json
import logging
from typing import Any, Iterable

from models import ImageMetadata

logger = logging.getLogger("feature_geometry")

EXPECTED_VERSION = 1
GRID_SIZE = 32


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

    version = payload.get("version")
    if version != EXPECTED_VERSION:
        return False, "Invalid feature geometry version."

    grid = payload.get("grid")
    if not isinstance(grid, dict):
        return False, "Invalid feature geometry payload."
    if grid.get("rows") != GRID_SIZE or grid.get("cols") != GRID_SIZE:
        return False, "Invalid feature geometry grid."

    items = payload.get("items")
    if not isinstance(items, list):
        return False, "Invalid feature geometry payload."

    allowed_features = set(selected_feature_ids or [])
    if items and not allowed_features:
        return False, "Feature geometry does not match selected features."

    width = image_metadata.width if image_metadata else None
    height = image_metadata.height if image_metadata else None

    for item in items:
        if not isinstance(item, dict):
            return False, "Invalid feature geometry payload."

        feature_id = item.get("feature_id")
        if not isinstance(feature_id, int):
            return False, "Invalid feature geometry payload."
        if feature_id not in allowed_features:
            return False, "Feature geometry does not match selected features."

        roi = item.get("roi")
        polygon = item.get("polygon")
        mask = item.get("mask")

        if not isinstance(roi, dict) or not isinstance(polygon, dict) or not isinstance(mask, dict):
            return False, "Invalid feature geometry payload."

        if roi.get("type") != "box":
            return False, "Invalid geometry type submitted."

        roi_pixel_points = roi.get("pixel")
        roi_norm_points = roi.get("norm")
        polygon_pixel_points = polygon.get("pixel")
        polygon_norm_points = polygon.get("norm")

        if not (_is_point_list(roi_pixel_points, min_len=2, exact_len=2) and _is_point_list(roi_norm_points, min_len=2, exact_len=2)):
            return False, "Invalid ROI coordinates submitted."
        if not (_is_point_list(polygon_pixel_points, min_len=3) and _is_point_list(polygon_norm_points, min_len=3)):
            return False, "Invalid geometry coordinates submitted."

        if width is not None and height is not None:
            if not _points_within_bounds(roi_pixel_points, width, height):
                return False, "Geometry coordinates are outside image bounds."
            if not _points_within_bounds(polygon_pixel_points, width, height):
                return False, "Geometry coordinates are outside image bounds."

        if not _points_within_unit_square(roi_norm_points):
            return False, "Normalized geometry coordinates are out of range."
        if not _points_within_unit_square(polygon_norm_points):
            return False, "Normalized geometry coordinates are out of range."

        if not _points_within_roi(polygon_pixel_points, roi_pixel_points):
            return False, "Polygon points must stay within ROI bounds."
        if not _points_within_roi(polygon_norm_points, roi_norm_points):
            return False, "Polygon points must stay within ROI bounds."

        if not _validate_mask(mask):
            return False, "Invalid mask cells submitted."

    return True, ""


def prepare_feature_geometry_for_storage(
    payload: dict | None,
    image_metadata: ImageMetadata | None,
    feature_metadata_by_id: dict[int, dict[str, Any]] | None = None,
) -> dict | None:
    """Normalize geometry payload and embed export-friendly derived fields."""
    if payload is None:
        return None

    normalized_items: list[dict[str, Any]] = []
    feature_metadata_by_id = feature_metadata_by_id or {}
    width = image_metadata.width if image_metadata else None
    height = image_metadata.height if image_metadata else None

    for item in payload.get("items", []):
        feature_id = int(item["feature_id"])
        roi = item["roi"]
        polygon = item["polygon"]
        mask = item["mask"]

        roi_pixel = _normalize_points(roi["pixel"])
        roi_norm = _normalize_points(roi["norm"])
        polygon_pixel = _normalize_points(polygon["pixel"])
        polygon_norm = _normalize_points(polygon["norm"])
        mask_cells = _normalize_cells(mask.get("cells", []))

        roi_bbox_pixel = _bbox_from_points(roi_pixel)
        roi_bbox_norm = _bbox_from_points(roi_norm)

        dicom_payload = item.get("dicom") if isinstance(item.get("dicom"), dict) else {}
        tracking_id = dicom_payload.get("tracking_id") or f"feature-{feature_id}"
        feature_meta = feature_metadata_by_id.get(feature_id, {})

        normalized_item: dict[str, Any] = {
            "feature_id": feature_id,
            "feature_label": feature_meta.get("label"),
            "feature_sr_no": feature_meta.get("sr_no"),
            "roi": {
                "type": "box",
                "pixel": roi_pixel,
                "norm": roi_norm,
            },
            "polygon": {
                "pixel": polygon_pixel,
                "norm": polygon_norm,
            },
            "mask": {
                "rows": GRID_SIZE,
                "cols": GRID_SIZE,
                "cells": mask_cells,
            },
            "export": {
                "bbox_pixel_xyxy": roi_bbox_pixel,
                "bbox_norm_xyxy": roi_bbox_norm,
                "yolo_bbox_xywh": _xyxy_to_xywh(roi_bbox_norm),
                "yolo_polygon_norm": _flatten_points(polygon_norm),
            },
            "dicom": {
                "tracking_id": tracking_id,
                "tracking_uid": dicom_payload.get("tracking_uid"),
                "finding_code": dicom_payload.get("finding_code"),
                "finding_site_code": dicom_payload.get("finding_site_code"),
            },
        }
        normalized_items.append(normalized_item)

    normalized_items.sort(key=lambda entry: (entry["feature_id"], entry["export"]["bbox_norm_xyxy"]))

    normalized_payload: dict[str, Any] = {
        "version": EXPECTED_VERSION,
        "grid": {"rows": GRID_SIZE, "cols": GRID_SIZE},
        "items": normalized_items,
        "export_meta": {
            "dicom_ready": True,
            "ai_ready": True,
        },
    }

    if width is not None and height is not None:
        normalized_payload["image"] = {"width": width, "height": height}

    return normalized_payload


def _is_point_list(value: Any, min_len: int = 1, exact_len: int | None = None) -> bool:
    if not isinstance(value, list) or not value:
        return False
    if exact_len is not None and len(value) != exact_len:
        return False
    if len(value) < min_len:
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


def _points_within_roi(points: list, roi_points: list) -> bool:
    x_values = [p[0] for p in roi_points]
    y_values = [p[1] for p in roi_points]
    min_x = min(x_values)
    max_x = max(x_values)
    min_y = min(y_values)
    max_y = max(y_values)
    for x, y in points:
        if x < min_x or x > max_x or y < min_y or y > max_y:
            return False
    return True


def _validate_mask(mask: dict) -> bool:
    rows = mask.get("rows")
    cols = mask.get("cols")
    cells = mask.get("cells")
    if rows != GRID_SIZE or cols != GRID_SIZE:
        return False
    if not isinstance(cells, list):
        return False

    seen: set[tuple[int, int]] = set()
    for cell in cells:
        if not isinstance(cell, (list, tuple)) or len(cell) != 2:
            return False
        row, col = cell
        if not isinstance(row, int) or not isinstance(col, int):
            return False
        if row < 0 or col < 0 or row >= rows or col >= cols:
            return False
        key = (row, col)
        if key in seen:
            return False
        seen.add(key)
    return True


def _normalize_points(points: list) -> list[list[float]]:
    normalized: list[list[float]] = []
    for x, y in points:
        normalized.append([float(x), float(y)])
    return normalized


def _normalize_cells(cells: list) -> list[list[int]]:
    unique_cells = sorted({(int(cell[0]), int(cell[1])) for cell in cells})
    return [[row, col] for row, col in unique_cells]


def _bbox_from_points(points: list[list[float]]) -> list[float]:
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return [min(xs), min(ys), max(xs), max(ys)]


def _xyxy_to_xywh(xyxy: list[float]) -> list[float]:
    x1, y1, x2, y2 = xyxy
    width = x2 - x1
    height = y2 - y1
    center_x = x1 + (width / 2.0)
    center_y = y1 + (height / 2.0)
    return [center_x, center_y, width, height]


def _flatten_points(points: list[list[float]]) -> list[float]:
    flattened: list[float] = []
    for x, y in points:
        flattened.extend([x, y])
    return flattened
