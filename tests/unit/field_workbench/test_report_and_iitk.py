"""Remidio report decoupling, and IITK's no-AI shape."""
from uuid import uuid4

from encounter_sets.models import EncounterSetAttachment
from field_workbench.status import remidio_report


def _attachment(encounter_id, *, metadata=None):
    return EncounterSetAttachment(
        uuid=str(uuid4()),
        patient_encounter_id=encounter_id,
        original_filename="report.pdf",
        folder_rel="field/report",
        asset_kind="pdf",
        mime_type="application/pdf",
        creates_task=False,
        metadata_json=metadata or {},
    )


def test_pdf_is_offered_before_ocr_has_run(db_session, field_data):
    """Gating the PDF on OCR would withhold a report the user could already read."""
    encounter = field_data["encounter"]
    db_session.add(_attachment(encounter.id))
    db_session.flush()
    db_session.refresh(encounter)

    report = remidio_report(encounter, pdf_url="/pdf")

    assert report.pdf_available is True
    assert report.pdf_url == "/pdf"
    assert report.ocr_status == "pending"
    assert report.ocr_result is None


def test_structured_result_appears_once_ocr_completes(db_session, field_data):
    encounter = field_data["encounter"]
    db_session.add(
        _attachment(
            encounter.id,
            metadata={
                "ocr": {
                    "status": "completed",
                    "dr_report": {"result": "Moderate NPDR"},
                    "completed_at": "2026-08-20T10:00:00+00:00",
                }
            },
        )
    )
    db_session.flush()
    db_session.refresh(encounter)

    report = remidio_report(encounter, pdf_url="/pdf")

    assert report.ocr_status == "completed"
    assert report.ocr_result == "Moderate NPDR"
    # The PDF stays reachable after OCR, not replaced by it.
    assert report.pdf_available is True


def test_failed_ocr_is_reported_without_hiding_the_pdf(db_session, field_data):
    encounter = field_data["encounter"]
    db_session.add(_attachment(encounter.id, metadata={"ocr": {"status": "failed"}}))
    db_session.flush()
    db_session.refresh(encounter)

    report = remidio_report(encounter, pdf_url="/pdf")

    assert report.ocr_status == "failed"
    assert report.pdf_available is True


def test_no_attachment_means_no_report_block_at_all(db_session, field_data):
    report = remidio_report(field_data["encounter"], pdf_url="/pdf")
    assert report is None


def test_iitk_encounters_carry_no_ai_and_no_report(client, auth_headers, db_session, field_data):
    """IITK has no AI models configured, so an empty AI list is correct, not an error."""
    encounter = field_data["encounter"]
    encounter.metadata_json = {"upload": {"source_kind": "iitk_api"}}
    db_session.flush()

    response = client.get(
        f"/api/mobile/v1/field/encounters/{encounter.uuid}", headers=auth_headers
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["source"] == "iitk"
    assert payload["ai"] == []
    assert payload["report"] is None


def test_requesting_inference_on_an_iitk_encounter_is_a_typed_conflict(
    client, auth_headers, db_session, field_data
):
    encounter = field_data["encounter"]
    encounter.metadata_json = {"upload": {"source_kind": "iitk_api"}}
    db_session.flush()

    response = client.post(
        f"/api/mobile/v1/field/encounters/{encounter.uuid}/inference",
        json={"workflows": ["dr_dme"]},
        headers=auth_headers,
    )

    assert response.status_code == 409
    assert response.get_json()["error"] == "no_ai_configured"


def test_a_later_pending_attachment_does_not_undo_a_completed_report(db_session, field_data):
    """Encounters carry several attachments; one still queued must not mask a result."""
    encounter = field_data["encounter"]
    db_session.add(
        _attachment(
            encounter.id,
            metadata={"ocr": {"status": "completed", "dr_report": {"result": "Mild DR"}}},
        )
    )
    db_session.add(_attachment(encounter.id, metadata={"ocr": {"status": "queued"}}))
    db_session.flush()
    db_session.refresh(encounter)

    report = remidio_report(encounter, pdf_url="/pdf")

    assert report.ocr_status == "completed"
    assert report.ocr_result == "Mild DR"
