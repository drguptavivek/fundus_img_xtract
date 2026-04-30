import pytest

from remidio_api_integration.errors import RemidioConfigError
from remidio_api_integration.service import upsert_routing_rule
from models import RemidioConnection


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
