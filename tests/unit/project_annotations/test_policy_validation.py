import pytest

from project_annotations.errors import AnnotationPolicyValidationError
from project_annotations.service import parse_policy_update


def _payload():
    return {
        "revision": 0,
        "enabled": True,
        "enabled_tools": ["box", "polygon"],
        "default_feature_policy": {
            "localization": "box_or_segmentation",
            "preferred_tool": "box",
            "allowed_tools": ["box", "polygon"],
        },
        "project_classes": [],
    }


def test_rejects_unsupported_preferred_tool_before_database_write():
    payload = _payload()
    payload["default_feature_policy"]["preferred_tool"] = "freehand"

    with pytest.raises(AnnotationPolicyValidationError, match="is unsupported"):
        parse_policy_update(payload)


def test_rejects_duplicate_project_class_keys():
    payload = _payload()
    project_class = {
        "key": "optic_disc",
        "localization": "segmentation",
        "multiple_instances": False,
        "active": True,
    }
    payload["project_classes"] = [project_class, dict(project_class)]

    with pytest.raises(AnnotationPolicyValidationError, match="keys must be unique"):
        parse_policy_update(payload)


def test_rejects_class_key_that_is_not_already_snake_case():
    payload = _payload()
    payload["project_classes"] = [
        {
            "key": "Optic_Disc",
            "localization": "segmentation",
            "multiple_instances": False,
            "active": True,
        }
    ]

    with pytest.raises(AnnotationPolicyValidationError, match="must be snake-case"):
        parse_policy_update(payload)


def test_project_class_uses_only_simple_project_level_fields():
    payload = _payload()
    payload["project_classes"] = [
        {
            "key": "lesion",
            "localization": "box",
            "multiple_instances": False,
            "active": True,
        }
    ]

    update = parse_policy_update(payload)

    assert update.project_classes[0].multiple_instances is False
    assert update.project_classes[0].key == "lesion"


def test_project_class_rejects_removed_per_class_configuration_fields():
    payload = _payload()
    payload["project_classes"] = [
        {
            "key": "lesion",
            "localization": "box",
            "multiple_instances": False,
            "active": True,
            "preferred_tool": "box",
        }
    ]

    with pytest.raises(AnnotationPolicyValidationError, match="unsupported fields: preferred_tool"):
        parse_policy_update(payload)


def test_project_class_rejects_negative_display_order():
    payload = _payload()
    payload["project_classes"] = [
        {
            "key": "lesion",
            "localization": "box",
            "display_order": -1,
            "multiple_instances": False,
            "active": True,
        }
    ]

    with pytest.raises(AnnotationPolicyValidationError, match="non-negative integer"):
        parse_policy_update(payload)


def test_rect_is_a_distinct_supported_segmentation_tool():
    payload = _payload()
    payload["enabled_tools"] = ["box", "rect", "polygon"]
    payload["default_feature_policy"]["allowed_tools"] = ["box", "rect", "polygon"]
    payload["default_feature_policy"]["preferred_tool"] = "rect"

    update = parse_policy_update(payload)

    assert update.enabled_tools == ("box", "rect", "polygon")
    assert update.preferred_tool == "rect"
