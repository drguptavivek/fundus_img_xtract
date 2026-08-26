import pytest

from remidio_api_integration.errors import RemidioConfigError
from remidio_api_integration import service
from remidio_api_integration.service import upsert_routing_rule
from models import RemidioConnection


def test_remidio_post_processing_dispatches_every_workflow(monkeypatch):
    ingest_result = {"groups": [{"ingest": {"exams": []}}]}
    calls = []

    monkeypatch.setattr(
        service,
        "_queue_encounter_set_image_post_processing",
        lambda result, *, user_id: calls.append(("images", result, user_id)) or {"images_queued": 2},
    )
    monkeypatch.setattr(
        service,
        "_queue_encounter_set_attachment_pdf_ocr",
        lambda result, *, user_id: calls.append(("pdf", result, user_id)) or {"pdf_ocr_queued": 1},
    )
    monkeypatch.setattr(
        service,
        "_queue_encounter_set_ai_inference",
        lambda result, *, user_id: calls.append(("ai", result, user_id)) or {"wadhwani_tasks_queued": 3},
    )
    monkeypatch.setattr(
        service,
        "_bump_field_cache_for_ingest",
        lambda result: calls.append(("cache", result, None)),
    )

    queued = service._queue_remidio_api_post_processing(ingest_result, user_id=41)

    assert queued == {
        "images_queued": 2,
        "pdf_ocr_queued": 1,
        "wadhwani_tasks_queued": 3,
    }
    assert calls == [
        ("images", ingest_result, 41),
        ("pdf", ingest_result, 41),
        ("ai", ingest_result, 41),
        ("cache", ingest_result, None),
    ]


def test_upsert_routing_rule_requires_site_custom_identifier(db_session, core_test_data):
    lab_unit = core_test_data["lab_unit"]
    camera = core_test_data["camera"]
    connection = RemidioConnection(
        name="Test Remidio",
        base_url="https://example.test",
        client_name="PACS_GATEWAY",
        client_identification_token_encrypted="encrypted",
        email_encrypted="encrypted",
        password_encrypted="encrypted",
        secret_salt="a" * 64,
        active=True,
    )
    db_session.add(connection)
    db_session.flush()

    with pytest.raises(RemidioConfigError, match="site_custom_identifier"):
        upsert_routing_rule(
            db_session,
            {
                "remidio_connection_id": connection.id,
                "site_custom_identifier": "",
                "remidio_device_type": "FOP",
                "project_id": 1,
                "lab_unit_id": lab_unit.id,
                "camera_id": camera.id,
            },
        )
