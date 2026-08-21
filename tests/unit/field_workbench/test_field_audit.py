"""The field surface records who read patient data and who spent money."""
from sqlalchemy import select

from field_workbench import audit as field_audit
from models import SensitiveOperationAudit

from tests.unit.field_workbench.conftest import CAPTURE_DATE


def _rows(db_session, operation_type):
    return db_session.execute(
        select(SensitiveOperationAudit).where(
            SensitiveOperationAudit.operation_type == operation_type
        )
    ).scalars().all()


def test_reading_the_queue_is_audited(client, auth_headers, db_session, field_data):
    client.get(
        f"/api/mobile/v1/field/projects/{field_data['project'].id}/encounters",
        query_string={"date": CAPTURE_DATE.isoformat()},
        headers=auth_headers,
    )

    rows = _rows(db_session, field_audit.OPERATION_QUEUE_READ)
    assert rows, "a queue read must leave an audit trail"
    row = rows[-1]
    assert row.user_id == field_data["user"].id
    assert row.get_request_details()["project_id"] == field_data["project"].id


def test_opening_an_encounter_is_audited(client, auth_headers, db_session, field_data):
    client.get(
        f"/api/mobile/v1/field/encounters/{field_data['encounter'].uuid}",
        headers=auth_headers,
    )

    rows = _rows(db_session, field_audit.OPERATION_DETAIL_READ)
    assert rows
    assert rows[-1].get_request_details()["encounter_uuid"] == field_data["encounter"].uuid


def test_requesting_inference_is_audited_even_when_policy_refuses_it(
    client, auth_headers, db_session, field_data
):
    """A refused request still records who asked, and why it was declined."""
    client.post(
        f"/api/mobile/v1/field/encounters/{field_data['encounter'].uuid}/inference",
        json={"workflows": ["dr_dme"]},
        headers=auth_headers,
    )

    rows = _rows(db_session, field_audit.OPERATION_INFERENCE_REQUEST)
    assert rows
    result = rows[-1].get_result_details()
    assert result["dr_dme"]["queued"] is False
    assert result["dr_dme"]["reason"] == "workflow_disabled"


def test_a_failing_audit_write_never_breaks_the_read(db_session, monkeypatch):
    """Refusing a clinical read because auditing failed would be the worse outcome."""
    monkeypatch.setattr(
        field_audit, "SensitiveOperationAudit", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    field_audit.record(db_session, user_id=1, operation_type="field_test")
