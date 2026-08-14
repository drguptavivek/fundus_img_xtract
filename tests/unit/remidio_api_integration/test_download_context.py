from types import SimpleNamespace

from remidio_api_integration.ingest import _download_context


def test_download_context_contains_routing_and_encounter_lineage_without_patient_identifiers():
    exam = SimpleNamespace(
        id=812,
        remidio_connection_id=2,
        site_custom_identifier="comoph_4394",
        remidio_exam_id="6487588646944768",
    )
    binding = SimpleNamespace(
        id=19,
        routing_profile_id=3,
        routing_profile=SimpleNamespace(name="Prospective Retina"),
        remidio_api_source_rule_id=7,
        project_upload_profile_id=11,
        lab_unit_id=4,
        camera_id=2,
    )
    encounter = SimpleNamespace(id=3936, project_id=3)

    context = _download_context(
        exam=exam,
        binding=binding,
        encounter=encounter,
        asset_type="image",
        remidio_asset_row_id=11162,
        remidio_asset_id="6025072208773120",
        device_type="FOP",
    ).as_dict()

    assert context == {
        "routing_profile_id": 3,
        "routing_profile_name": "Prospective Retina",
        "remidio_api_binding_id": 19,
        "remidio_api_source_rule_id": 7,
        "project_id": 3,
        "project_upload_profile_id": 11,
        "lab_unit_id": 4,
        "camera_id": 2,
        "connection_id": 2,
        "site_custom_identifier": "comoph_4394",
        "patient_encounter_id": 3936,
        "remidio_exam_row_id": 812,
        "remidio_exam_id": "6487588646944768",
        "asset_type": "image",
        "remidio_asset_row_id": 11162,
        "remidio_asset_id": "6025072208773120",
        "device_type": "FOP",
    }
    assert "mrn" not in context
    assert "patient_id" not in context
