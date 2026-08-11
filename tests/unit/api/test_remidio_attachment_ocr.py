from api.remidio_api_integration import _attachment_ocr_payload
from encounter_sets.models import EncounterSetAttachment


def test_attachment_ocr_status_payload_includes_amd_report():
    attachment = EncounterSetAttachment(
        patient_encounter_id=1,
        asset_kind="pdf",
        original_filename="aiReport.pdf",
        stored_filename="aiReport.pdf",
        folder_rel="files/test",
        metadata_json={
            "ocr": {
                "status": "completed",
                "amd_report": {
                    "detected": True,
                    "page": 1,
                    "amd_data": {"result": "Signs of AMD detected."},
                },
            }
        },
    )

    payload = _attachment_ocr_payload(attachment, queued=False)

    assert payload["status"] == "completed"
    assert payload["amd_report"]["page"] == 1
    assert payload["amd_report"]["amd_data"]["result"] == "Signs of AMD detected."
