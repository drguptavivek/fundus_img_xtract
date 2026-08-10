from project_annotations.contracts import (
    AnnotationContextDTO,
    FeaturePolicyDTO,
    ResolvedProjectClassDTO,
)
from project_annotations.service import validate_geometry_policy


def _context():
    return AnnotationContextDTO(
        policy_source="project",
        project_id=7,
        enabled=True,
        revision=3,
        enabled_tools=("box", "polygon"),
        default_feature_policy=FeaturePolicyDTO(
            localization="box_or_segmentation",
            preferred_tool="box",
            allowed_tools=("box", "polygon"),
        ),
        project_classes=(
            ResolvedProjectClassDTO(
                id=11,
                key="optic_disc",
                localization="segmentation",
                display_order=10,
                multiple_instances=False,
                active=True,
            ),
        ),
    )


def _item():
    return {
        "class_source": "project_class",
        "project_class_id": 11,
        "project_class_key": "optic_disc",
        "geometry_type": "polygon",
    }


def test_accepts_compatible_project_class_annotation():
    valid, error = validate_geometry_policy(
        {"policy_revision": 3, "items": [_item()]}, _context()
    )
    assert valid is True
    assert error == ""


def test_rejects_stale_policy_and_single_class_duplicates():
    valid, error = validate_geometry_policy(
        {"policy_revision": 2, "items": [_item()]}, _context()
    )
    assert valid is False
    assert "changed" in error

    valid, error = validate_geometry_policy(
        {"policy_revision": 3, "items": [_item(), _item()]}, _context()
    )
    assert valid is False
    assert "only one" in error


def test_rejects_tool_incompatible_with_class_localization():
    item = _item()
    item["geometry_type"] = "box"
    valid, error = validate_geometry_policy(
        {"policy_revision": 3, "items": [item]}, _context()
    )
    assert valid is False
    assert "incompatible" in error


def test_accepts_image_level_project_class_assertion():
    context = _context()
    image_level_class = ResolvedProjectClassDTO(
        id=12,
        key="gradable_field",
        localization="none",
        display_order=20,
        multiple_instances=False,
        active=True,
    )
    context = AnnotationContextDTO(
        **{**context.__dict__, "project_classes": context.project_classes + (image_level_class,)}
    )
    valid, error = validate_geometry_policy(
        {
            "policy_revision": 3,
            "items": [{
                "class_source": "project_class",
                "project_class_id": 12,
                "project_class_key": "gradable_field",
                "geometry_type": "none",
            }],
        },
        context,
    )
    assert valid is True
    assert error == ""
