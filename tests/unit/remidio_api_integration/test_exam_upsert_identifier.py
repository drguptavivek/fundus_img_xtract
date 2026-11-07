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


def test_competing_exam_insert_is_reused_without_aborting_transaction(db_session, connection, monkeypatch):
    """An exam appearing immediately before INSERT must take the conflict path."""
    original_execute = db_session.execute
    competing_ids = []

    def execute_after_competing_insert(statement, *args, **kwargs):
        from sqlalchemy.dialects.postgresql import Insert

        if isinstance(statement, Insert) and not competing_ids:
            competing = RemidioExam(
                remidio_connection_id=connection.id,
                remidio_exam_id="exam-1",
                site_custom_identifier="comoph_4834",
                pull_source="getExamsByDate",
            )
            db_session.add(competing)
            db_session.flush()
            competing_ids.append(competing.id)
        return original_execute(statement, *args, **kwargs)

    monkeypatch.setattr(db_session, "execute", execute_after_competing_insert)
    summary = upsert_exam_payloads(
        db_session,
        connection_id=connection.id,
        payloads=[_payload(site_custom_identifier=None, pull_source="getPatientWithLastExam")],
    )
    assert summary.exams_created == 0
    assert summary.exams_updated == 1
    exam = db_session.query(RemidioExam).filter_by(id=competing_ids[0]).one()
    assert exam.site_custom_identifier == "comoph_4834"
    assert exam.pull_source == "getPatientWithLastExam"
    assert db_session.is_active


def test_repeated_exam_in_one_pull_is_counted_as_update(db_session, connection):
    from dataclasses import replace
    from models import RemidioImage, RemidioReport
    from remidio_api_integration.schemas import RemidioImagePayload, RemidioReportPayload

    payload = _payload(site_custom_identifier="comoph_4834", pull_source="getExamsByDate")
    payload = replace(
        payload,
        images=[RemidioImagePayload(
            remidio_image_id="image-1", device_type="FOP", image_bucket=None,
            image_variant=None, laterality=None, field=None, quality=None,
            width=None, height=None, remidio_path=None, remidio_thumbnail_path=None,
            raw_json={},
        )],
        reports=[RemidioReportPayload(
            remidio_report_id="report-1", report_type="DR", report_local_id=None,
            generated_date_ms=None, generated_at=None, remidio_path=None, raw_json={},
        )],
    )
    summary = upsert_exam_payloads(db_session, connection_id=connection.id, payloads=[payload, payload])
    assert summary.exams_created == 1
    assert summary.exams_updated == 1
    assert summary.images_created == summary.images_updated == 1
    assert summary.reports_created == summary.reports_updated == 1
    assert db_session.query(RemidioExam).filter_by(remidio_connection_id=connection.id).count() == 1
    exam = db_session.query(RemidioExam).filter_by(remidio_connection_id=connection.id).one()
    assert db_session.query(RemidioImage).filter_by(remidio_exam_id=exam.id).count() == 1
    assert db_session.query(RemidioReport).filter_by(remidio_exam_id=exam.id).count() == 1
