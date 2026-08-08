from types import SimpleNamespace

from upload_profiles.image_task_routing import (
    image_metadata_matches_rule,
    missing_image_task_routing_fields,
    required_image_task_routing_fields,
)


def test_image_metadata_rule_is_optional_and_matches_exact_scalar_values():
    assert image_metadata_matches_rule({"laterality": "OD"}, None) is True
    assert image_metadata_matches_rule(
        {"laterality": "OD"},
        {"field_key": "laterality", "match_value": "OD"},
    ) is True
    assert image_metadata_matches_rule(
        {"laterality": "OS"},
        {"field_key": "laterality", "match_value": "OD"},
    ) is False
    assert image_metadata_matches_rule(
        {},
        {"field_key": "laterality", "match_value": "OD"},
    ) is False


def test_image_metadata_rule_supports_multi_value_and_boolean_fields():
    assert image_metadata_matches_rule(
        {"tags": ["disc", "macula"]},
        {"field_key": "tags", "match_value": "macula"},
    ) is True
    assert image_metadata_matches_rule(
        {"is_montage": True},
        {"field_key": "is_montage", "match_value": "true"},
    ) is True


def _routing_config(*, policy="always", package_active=True, scheme_active=True):
    return SimpleNamespace(
        encounter_set_type=SimpleNamespace(
            metadata_schema_json={
                "fields": [
                    {"key": "laterality", "label": "Laterality", "scope": "image"},
                    {"key": "site_code", "label": "Site", "scope": "encounter"},
                ]
            }
        ),
        grading_packages=[
            SimpleNamespace(
                active=package_active,
                applicability="always",
                image_grading_schemes=[
                    SimpleNamespace(
                        active=scheme_active,
                        auto_create_policy=policy,
                        metadata_field_key="laterality",
                        metadata_match_value="OD",
                    )
                ],
            )
        ],
    )


def _task_image(**overrides):
    values = {
        "asset_kind": "clinical_image",
        "creates_task": True,
        "visible_to_grader": True,
        "is_not_gradable": False,
        "metadata_json": {},
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_required_routing_fields_come_from_active_auto_creation_rules():
    fields = required_image_task_routing_fields(_routing_config())

    assert [(field.key, field.label) for field in fields] == [("laterality", "Laterality")]
    assert required_image_task_routing_fields(_routing_config(policy="never")) == ()
    assert required_image_task_routing_fields(_routing_config(package_active=False)) == ()
    assert required_image_task_routing_fields(_routing_config(scheme_active=False)) == ()


def test_missing_routing_fields_apply_only_to_gradable_task_images():
    config = _routing_config()

    assert [field.key for field in missing_image_task_routing_fields(_task_image(), config)] == ["laterality"]
    assert missing_image_task_routing_fields(
        _task_image(metadata_json={"laterality": "OD"}),
        config,
    ) == ()
    assert missing_image_task_routing_fields(_task_image(is_not_gradable=True), config) == ()
    assert missing_image_task_routing_fields(_task_image(creates_task=False), config) == ()
    assert missing_image_task_routing_fields(_task_image(visible_to_grader=False), config) == ()
