from upload_profiles.image_task_routing import image_metadata_matches_rule


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
