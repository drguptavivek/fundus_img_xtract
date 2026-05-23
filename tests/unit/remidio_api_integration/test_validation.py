from datetime import timezone

import pytest

from remidio_api_integration.errors import RemidioValidationError
from remidio_api_integration.validation import extract_exam_payloads, normalize_date, require_token, sanitize_for_storage


def test_normalize_date_accepts_remidio_and_iso_formats():
    assert normalize_date("30-04-2026") == "30-04-2026"
    assert normalize_date("2026-04-30") == "30-04-2026"


def test_normalize_date_rejects_ambiguous_input():
    with pytest.raises(RemidioValidationError):
        normalize_date("04/30/2026")


def test_require_token_accepts_direct_data_token():
    assert require_token({"status": {"statusCode": "OK"}, "data": "token-value"}) == "token-value"


def test_extract_exam_payloads_maps_exam_images_reports_and_preserves_raw_metadata():
    payloads = extract_exam_payloads(
        [
            {
                "patientDetails": {
                    "id": 6547105862647808,
                    "mrn": "17136192",
                    "siteId": 5504695309172736,
                    "firstName": "Hidden",
                    "lastName": "Patient",
                },
                "examDetails": {
                    "id": 4613839312125952,
                    "localId": "REM-2255::1775022627",
                    "examCustomId": "17",
                    "examDate": 1775022627123,
                    "examState": "ACTIVE",
                    "deviceType": ["FOP"],
                },
                "images": {
                    "fopImages": {
                        "STANDARD": [
                            {
                                "id": 6396051191758848,
                                "deviceType": "FOP",
                                "field": "DISC",
                                "laterality": "RIGHT",
                                "quality": "SUFFICIENT",
                                "width": 2866,
                                "height": 2866,
                                "path": "org/site/patient/exam/FOP/images/file",
                                "thumbnailPath": "org/site/patient/exam/thumbnail-images/file",
                            }
                        ],
                        "EDITED": [],
                    }
                },
                "mediosAIReport": {
                    "id": 4523900784345088,
                    "examId": 4613839312125952,
                    "localId": "REM-2255::1775022627-medios-ai-report",
                    "generatedDate": 1775022829192,
                    "path": "org/site/patient/exam/medios-ai-reports/file",
                },
            }
        ],
        site_custom_identifier="rpc_comoph_2",
        pull_source="getExamsByDate",
    )

    assert len(payloads) == 1
    exam = payloads[0]
    assert exam.remidio_exam_id == "4613839312125952"
    assert exam.site_custom_identifier == "rpc_comoph_2"
    assert exam.remidio_numeric_site_id == "5504695309172736"
    assert exam.remidio_patient_mrn == "17136192"
    assert exam.exam_local_id == "REM-2255::1775022627"
    assert exam.exam_date is not None
    assert exam.exam_date.tzinfo == timezone.utc
    assert exam.device_types == ["FOP"]
    assert exam.raw_json["patientDetails"]["firstName"] == "Hidden"
    assert exam.raw_json["patientDetails"]["lastName"] == "Patient"
    assert exam.raw_json["images"]["fopImages"]["STANDARD"][0]["path"] == "org/site/patient/exam/FOP/images/file"

    assert len(exam.images) == 1
    image = exam.images[0]
    assert image.remidio_image_id == "6396051191758848"
    assert image.image_bucket == "fopImages"
    assert image.image_variant == "STANDARD"
    assert image.field == "DISC"
    assert image.laterality == "RIGHT"

    assert len(exam.reports) == 1
    report = exam.reports[0]
    assert report.remidio_report_id == "4523900784345088"
    assert report.report_type == "mediosAIReport"
    assert report.generated_at is not None


def test_sanitize_for_storage_redacts_credentials_but_not_source_identity():
    stored = sanitize_for_storage(
        {
            "firstName": "Visible",
            "email": "person@example.org",
            "path": "https://example.org/signed/path?X-Goog-Signature=value",
            "clientAuthToken": "secret-token",
            "nested": {"accessToken": "secret-access"},
        }
    )

    assert stored["firstName"] == "Visible"
    assert stored["email"] == "person@example.org"
    assert stored["path"].startswith("https://example.org/signed/path")
    assert stored["clientAuthToken"] == "[redacted]"
    assert stored["nested"]["accessToken"] == "[redacted]"
