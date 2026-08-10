from __future__ import annotations

from types import SimpleNamespace
import base64
import struct

import pytest

from grading.workbench.annotations import _bbox, _instances_from_geometry, parse_grade_observation
from grading.workbench.errors import AnnotationPolicyChanged, AnnotationValidationError


def test_normalized_box_becomes_independent_annotation_instance():
    geometry = {
        "items": [{
            "instance_uuid": "7c87b1fb-a946-4cb8-aec4-e47f5b1dd470",
            "class_source": "grading_feature",
            "feature_id": 91,
            "geometry_type": "box",
            "roi": {"pixel": [[10, 20], [30, 55]]},
            "export": {"bbox_pixel_xyxy": [10, 20, 30, 55]},
        }]
    }

    instances = _instances_from_geometry(geometry, image_uuid="image-uuid")

    assert len(instances) == 1
    assert instances[0].grading_feature_id == 91
    assert instances[0].geometry_type == "box"
    assert _bbox(instances[0].geometry) == (10.0, 20.0, 20.0, 35.0)


def test_segmentation_instance_keeps_geometry_and_derived_box():
    item = {
        "class_source": "project_class",
        "project_class_id": 12,
        "project_class_key": "lesion",
        "geometry_type": "polygon",
        "polygon": {"pixel": [[2, 4], [8, 4], [8, 10]]},
        "export": {"bbox_pixel_xyxy": [2, 4, 8, 10]},
    }

    instance = _instances_from_geometry({"items": [item]}, image_uuid="image-uuid")[0]

    assert instance.geometry is item
    assert instance.project_class_id == 12
    assert _bbox(instance.geometry) == (2.0, 4.0, 6.0, 6.0)


def test_empty_geometry_still_requires_exact_policy_revision(monkeypatch):
    label = SimpleNamespace(id=3, disease_id=7)

    class Query:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return label

        def all(self):
            return []

    db = SimpleNamespace(query=lambda model: Query())
    task = SimpleNamespace(disease_id=7)
    context = SimpleNamespace(revision=4)
    monkeypatch.setattr("grading.workbench.annotations.resolve_task_annotation_context", lambda *_: context)

    with pytest.raises(AnnotationPolicyChanged):
        parse_grade_observation(
            db,
            task=task,
            label_id=3,
            comment=None,
            raw_selected_features=[],
            raw_feature_geometry="",
            submitted_policy_revision=3,
            existing_grade=None,
        )


def _png_header(width: int, height: int) -> str:
    payload = b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", width, height)
    return base64.b64encode(payload).decode("ascii")


def test_brush_segmentation_mask_tiles_are_validated_and_retained():
    tile = {
        "tile_x": 0,
        "tile_y": 1,
        "width": 32,
        "height": 16,
        "png_base64": _png_header(32, 16),
    }
    item = {
        "class_source": "grading_feature",
        "feature_id": 91,
        "geometry_type": "brush_mask",
        "mask_tiles": [tile],
    }

    instance = _instances_from_geometry({"items": [item]}, image_uuid="image-uuid")[0]

    assert instance.mask_tiles[0]["checksum"]
    assert instance.mask_tiles[0]["tile_y"] == 1


def test_mask_tile_rejects_claimed_dimensions_that_do_not_match_png():
    item = {
        "class_source": "grading_feature",
        "feature_id": 91,
        "geometry_type": "brush_mask",
        "mask_tiles": [{
            "tile_x": 0,
            "tile_y": 0,
            "width": 31,
            "height": 16,
            "png_base64": _png_header(32, 16),
        }],
    }

    with pytest.raises(AnnotationValidationError):
        _instances_from_geometry({"items": [item]}, image_uuid="image-uuid")
