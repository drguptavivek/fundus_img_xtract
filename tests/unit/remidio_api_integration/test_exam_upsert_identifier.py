"""A pull source that omits the site custom identifier must not erase it.

`getPatientWithLastExam` responses carry no site custom identifier, so a
single-patient re-pull used to blank the value a date pull had established.
Routing survived on the numeric-site fallback, which is what made this quiet.
"""
from uuid import uuid4

import pytest

from models import RemidioConnection, RemidioExam, RemidioSite
from remidio_api_integration.persistence import upsert_exam_payloads
from remidio_api_integration.schemas import RemidioExamPayload


@pytest.fixture
def connection(db_session):
    row = RemidioConnection(
        name=f"Remidio Upsert {uuid4()}",
        base_url="https://example.test",
        client_name="PACS_GATEWAY",
        client_identification_token_encrypted="encrypted",
        email_encrypted="encrypted",
        password_encrypted="encrypted",
        secret_salt="a" * 64,
        active=True,
    )
    db_session.add(row)
    db_session.flush()
    db_session.add(
        RemidioSite(
            remidio_connection_id=row.id,
            remidio_site_id="5733647311175680",
            site_custom_identifier="comoph_4834",
            active=True,
        )
    )
    db_session.flush()
    return row


def _payload(*, site_custom_identifier, pull_source, exam_id="exam-1"):
    return RemidioExamPayload(
        remidio_exam_id=exam_id,
        site_custom_identifier=site_custom_identifier,
        remidio_numeric_site_id="5733647311175680",
        remidio_patient_id="p1",
        remidio_patient_mrn="MRN-1",
        exam_local_id=None,
        exam_custom_id=None,
        device_types=["FOP"],
        exam_state="COMPLETE",
        exam_date_ms=None,
        exam_date=None,
        pull_source=pull_source,
        raw_json={},
        images=[],
        reports=[],
    )


def test_a_pull_without_an_identifier_keeps_the_existing_one(db_session, connection):
    upsert_exam_payloads(
        db_session,
        connection_id=connection.id,
        payloads=[_payload(site_custom_identifier="comoph_4834", pull_source="getExamsByDate")],
    )
    db_session.flush()

    # getPatientWithLastExam carries no identifier in its response body.
    upsert_exam_payloads(
        db_session,
        connection_id=connection.id,
        payloads=[_payload(site_custom_identifier=None, pull_source="getPatientWithLastExam")],
    )
    db_session.flush()

    exam = db_session.query(RemidioExam).filter_by(remidio_exam_id="exam-1").one()
    assert exam.site_custom_identifier == "comoph_4834"
    assert exam.pull_source == "getPatientWithLastExam"
    # The site link must survive too - routing falls back to it.
    assert exam.remidio_site_id is not None


def test_an_identifier_still_populates_when_absent(db_session, connection):
    upsert_exam_payloads(
        db_session,
        connection_id=connection.id,
        payloads=[_payload(site_custom_identifier=None, pull_source="getPatientWithLastExam")],
    )
    db_session.flush()
    exam = db_session.query(RemidioExam).filter_by(remidio_exam_id="exam-1").one()
    assert exam.site_custom_identifier is None

    upsert_exam_payloads(
        db_session,
        connection_id=connection.id,
        payloads=[_payload(site_custom_identifier="comoph_4834", pull_source="getExamsByDate")],
    )
    db_session.flush()

    db_session.refresh(exam)
    assert exam.site_custom_identifier == "comoph_4834"


def test_service_resolves_the_identifier_from_a_numeric_site_id(db_session, connection):
    """getPatientWithLastExam is called with the numeric id, so it needs translating."""
    from remidio_api_integration.service import _site_custom_identifier_for

    assert _site_custom_identifier_for(db_session, connection.id, "5733647311175680") == "comoph_4834"
    assert _site_custom_identifier_for(db_session, connection.id, "comoph_4834") == "comoph_4834"
    assert _site_custom_identifier_for(db_session, connection.id, "unknown-site") is None
    assert _site_custom_identifier_for(db_session, connection.id, "") is None
