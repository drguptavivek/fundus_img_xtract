from types import SimpleNamespace

import pytest

from utils.feature_geometry import (
    parse_feature_geometry_payload,
    prepare_feature_geometry_for_storage,
    validate_feature_geometry_payload,
)


def _valid_payload() -> dict:
    return {
        "version": 1,
        "grid": {"rows": 8, "cols": 8},
        "items": [
            {
                "feature_id": 101,
                "roi": {
                    "type": "box",
                    "pixel": [[100, 100], [500, 500]],
                    "norm": [[0.1, 0.1], [0.5, 0.5]],
                },
                "polygon": {
                    "pixel": [[120, 120], [400, 130], [320, 300]],
                    "norm": [[0.12, 0.12], [0.4, 0.13], [0.32, 0.3]],
                },
                "mask": {
                    "rows": 8,
                    "cols": 8,
                    "cells": [[1, 1], [1, 2], [2, 2]],
                },
            }
        ],
    }


def test_parse_rejects_invalid_json() -> None:
    assert parse_feature_geometry_payload("{not-json}") is None


def test_validate_accepts_v1_payload() -> None:
    payload = _valid_payload()
    image_meta = SimpleNamespace(width=1000, height=1000)
    is_valid, error = validate_feature_geometry_payload(payload, [101], image_meta)
    assert is_valid is True
    assert error == ""


def test_validate_rejects_wrong_version() -> None:
    payload = _valid_payload()
    payload["version"] = 2
    is_valid, error = validate_feature_geometry_payload(payload, [101], None)
    assert is_valid is False
    assert "version" in error.lower()


def test_validate_rejects_grid_below_minimum() -> None:
    payload = _valid_payload()
    payload["grid"] = {"rows": 2, "cols": 2}
    is_valid, error = validate_feature_geometry_payload(payload, [101], None)
    assert is_valid is False
    assert "grid" in error.lower()


def test_validate_rejects_polygon_outside_roi() -> None:
    payload = _valid_payload()
    payload["items"][0]["polygon"]["pixel"] = [[120, 120], [900, 130], [320, 300]]
    is_valid, error = validate_feature_geometry_payload(payload, [101], SimpleNamespace(width=1000, height=1000))
    assert is_valid is False
    assert "roi" in error.lower()


def test_validate_rejects_feature_mismatch() -> None:
    payload = _valid_payload()
    is_valid, error = validate_feature_geometry_payload(payload, [999], SimpleNamespace(width=1000, height=1000))
    assert is_valid is False
    assert "selected features" in error.lower()


def test_validate_rejects_invalid_mask_cells() -> None:
    payload = _valid_payload()
    payload["items"][0]["mask"]["cells"] = [[1, 1], [1, 1]]
    is_valid, error = validate_feature_geometry_payload(payload, [101], SimpleNamespace(width=1000, height=1000))
    assert is_valid is False
    assert "mask" in error.lower()


def test_validate_rejects_legacy_geom_payload() -> None:
    payload = {
        "version": 1,
        "grid": {"rows": 8, "cols": 8},
        "items": [
            {
                "feature_id": 101,
                "geom": {
                    "type": "polygon",
                    "pixel": [[1, 1], [2, 2], [3, 3]],
                    "norm": [[0.01, 0.01], [0.02, 0.02], [0.03, 0.03]],
                },
            }
        ],
    }
    is_valid, error = validate_feature_geometry_payload(payload, [101], SimpleNamespace(width=1000, height=1000))
    assert is_valid is False
    assert "payload" in error.lower()


def test_prepare_payload_includes_export_and_dicom_blocks() -> None:
    payload = _valid_payload()
    payload["items"][0]["dicom"] = {
        "tracking_uid": "2.25.123",
        "finding_code": {"scheme": "SCT", "value": "111", "meaning": "Finding"},
        "finding_site_code": {"scheme": "SCT", "value": "222", "meaning": "Retina"},
    }
    prepared = prepare_feature_geometry_for_storage(payload, SimpleNamespace(width=1000, height=1000))
    assert prepared is not None
    assert prepared["version"] == 1
    assert prepared["grid"] == {"rows": 8, "cols": 8}
    assert prepared["image"] == {"width": 1000, "height": 1000}
    assert prepared["export_meta"] == {"dicom_ready": True, "ai_ready": True}

    item = prepared["items"][0]
    assert item["dicom"]["tracking_uid"] == "2.25.123"
    assert item["dicom"]["tracking_id"] == "feature-101"
    assert item["export"]["bbox_norm_xyxy"] == [0.1, 0.1, 0.5, 0.5]
    assert item["export"]["yolo_bbox_xywh"] == pytest.approx([0.3, 0.3, 0.4, 0.4], abs=1e-9)
    assert item["export"]["yolo_polygon_norm"] == [0.12, 0.12, 0.4, 0.13, 0.32, 0.3]


def test_prepare_payload_embeds_feature_label_metadata() -> None:
    payload = _valid_payload()
    prepared = prepare_feature_geometry_for_storage(
        payload,
        SimpleNamespace(width=1000, height=1000),
        feature_metadata_by_id={
            101: {"label": "Hard Exudates", "sr_no": 7},
        },
    )
    item = prepared["items"][0]
    assert item["feature_id"] == 101
    assert item["feature_label"] == "Hard Exudates"
    assert item["feature_sr_no"] == 7


def test_prepare_payload_preserves_mask_precision() -> None:
    payload = _valid_payload()
    payload["grid"] = {"rows": 16, "cols": 16}
    payload["items"][0]["mask"]["rows"] = 16
    payload["items"][0]["mask"]["cols"] = 16
    prepared = prepare_feature_geometry_for_storage(payload, SimpleNamespace(width=1000, height=1000))
    assert prepared["grid"] == {"rows": 16, "cols": 16}
    assert prepared["items"][0]["mask"]["rows"] == 16
    assert prepared["items"][0]["mask"]["cols"] == 16


def test_validate_accepts_high_resolution_mask_grid() -> None:
    payload = _valid_payload()
    payload["grid"] = {"rows": 192, "cols": 192}
    payload["items"][0]["mask"]["rows"] = 192
    payload["items"][0]["mask"]["cols"] = 192
    payload["items"][0]["mask"]["cells"] = [[0, 0], [191, 191], [96, 96]]
    is_valid, error = validate_feature_geometry_payload(payload, [101], SimpleNamespace(width=1000, height=1000))
    assert is_valid is True
    assert error == ""


def test_project_class_geometry_does_not_require_selected_grading_feature() -> None:
    payload = _valid_payload()
    item = payload["items"][0]
    item.pop("feature_id")
    item.update(
        class_source="project_class",
        project_class_id=17,
        project_class_key="optic_disc",
        feature_label="optic_disc",
        geometry_type="polygon",
    )

    is_valid, error = validate_feature_geometry_payload(
        payload, [], SimpleNamespace(width=1000, height=1000)
    )

    assert is_valid is True
    assert error == ""


def test_prepare_project_class_geometry_snapshots_policy_identity() -> None:
    payload = _valid_payload()
    item = payload["items"][0]
    item.pop("feature_id")
    item.update(
        class_source="project_class",
        project_class_id=17,
        project_class_key="optic_disc",
        feature_label="Optic disc",
        geometry_type="polygon",
    )

    prepared = prepare_feature_geometry_for_storage(
        payload,
        SimpleNamespace(width=1000, height=1000),
        annotation_context={
            "policy_source": "project",
            "project_id": 9,
            "revision": 4,
        },
    )

    assert prepared["project_id"] == 9
    assert prepared["policy_revision"] == 4
    assert prepared["items"][0]["project_class_id"] == 17
    assert prepared["items"][0]["project_class_key"] == "optic_disc"
    assert "feature_id" not in prepared["items"][0]


def test_image_level_project_class_assertion_requires_no_geometry() -> None:
    payload = {
        "version": 1,
        "grid": {"rows": 8, "cols": 8},
        "items": [{
            "class_source": "project_class",
            "project_class_id": 22,
            "project_class_key": "gradable_field",
            "feature_label": "Gradable field",
            "geometry_type": "none",
        }],
    }
    is_valid, error = validate_feature_geometry_payload(payload, [], None)
    prepared = prepare_feature_geometry_for_storage(payload, None)

    assert is_valid is True
    assert error == ""
    assert prepared["items"][0]["geometry_type"] == "none"
    assert "export" not in prepared["items"][0]
