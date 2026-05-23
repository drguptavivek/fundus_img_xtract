from remidio_api_integration.mapper import map_exam_payload


def test_map_exam_payload_maps_fop_disc_quality_and_reports():
    mapped = map_exam_payload(
        {
            "patientDetails": {
                "id": 1,
                "mrn": "17119023",
                "firstName": "Hidden",
                "lastName": "Patient",
                "gender": "Female",
                "dateOfBirth": -568080000000,
                "siteId": 5504695309172736,
            },
            "examDetails": {
                "id": 2,
                "localId": "REM-2255::1776665512",
                "examCustomId": "17",
                "examDate": 1776665512667,
                "examState": "ACTIVE",
                "deviceType": ["FOP"],
                "reportDate": 0,
            },
            "creatingUser": {
                "email": "operator@example.test",
                "employeeId": "EMP-1",
                "firstName": "Operator",
                "lastName": "User",
                "organizationId": 5545378933899264,
                "roles": ["DOCTOR", "OPERATOR"],
                "siteId": 5504695309172736,
                "userId": 4813320817213440,
            },
            "images": {
                "fopImages": {
                    "STANDARD": [
                        {
                            "id": 3,
                            "localId": "1776665543",
                            "examId": 2,
                            "date": 1776665543398,
                            "deviceType": "FOP",
                            "laterality": "RIGHT",
                            "field": "MACULA",
                            "quality": "SUFFICIENT",
                            "isCropped": True,
                            "width": 2866,
                            "height": 2866,
                            "path": "https://signed.example/image",
                            "thumbnailPath": "https://signed.example/thumb",
                            "discQualityResults": {
                                "acceptableQuality": True,
                                "discPresent": True,
                                "qualityScore": 0.76904297,
                                "roiX": 0.66796875,
                                "roiY": 0.5175781,
                            },
                        }
                    ]
                }
            },
            "mediosAIReport": {
                "id": 4,
                "examId": 2,
                "localId": "REM-2255::1776665512-medios-ai-report",
                "generatedDate": 1776665718836,
                "path": "https://signed.example/report",
                "drResult": {
                    "confidence": 88,
                    "inputSufficient": True,
                    "qualitySufficient": True,
                    "suggestedRefer": False,
                    "numberOfHeatmapImages": 0,
                },
                "gmaResult": {
                    "leftEyeCdr": 0.39,
                    "rightEyeCdr": 0.5,
                    "suggestedRefer": False,
                    "patientLevelResult": "NO_REFER",
                },
            },
            "aiReport": {
                "id": 5,
                "examId": 2,
                "localId": "REM-2255::1776665512-ai-report",
                "generatedDate": 1776665718836,
                "path": "https://signed.example/ai-report",
                "confidence": 0,
                "inputSufficient": True,
                "qualitySufficient": True,
                "suggestedRefer": False,
                "numberOfHeatmapImages": 0,
                "leftEyeCdr": 0.0,
                "rightEyeCdr": 0.0,
            },
        },
        site_custom_identifier="rpc_comoph_2",
    )

    assert mapped.patient["hospital_UHID"] == "17119023"
    assert mapped.patient["sex"] == "female"
    assert mapped.patient["remidio_site_custom_identifier"] == "rpc_comoph_2"
    assert mapped.patient["remidio_patient_raw_metadata"]["mrn"] == "17119023"

    assert mapped.encounter["exam_code"] == "17"
    assert mapped.encounter["device_type"] == "FOP"
    assert mapped.encounter["has_medios_ai_report"] is True
    assert mapped.encounter["clinical_image_count"] == 1
    raw_user = mapped.encounter["remidio_encounter_raw_metadata"]["creatingUser"]
    assert raw_user["email"] == "operator@example.test"
    assert raw_user["firstName"] == "Operator"
    assert raw_user["organizationId"] == 5545378933899264
    assert raw_user["roles"] == ["DOCTOR", "OPERATOR"]
    assert raw_user["userId"] == 4813320817213440

    image = mapped.images[0].metadata
    assert image["laterality"] == "OD"
    assert image["fundus_field"] == "MACULA"
    assert image["disc_roi_x"] == 0.66796875
    assert image["disc_roi_y"] == 0.5175781
    assert image["remidio_image_raw_metadata"]["path"] == "https://signed.example/image"

    report = next(item.metadata for item in mapped.reports if item.report_type == "mediosAIReport")
    assert report["remidio_report_type"] == "mediosAIReport"
    assert report["ai_confidence"] == 88
    assert report["gma_left_eye_cdr"] == 0.39
    assert report["gma_patient_level_result"] == "NO_REFER"
    assert report["remidio_report_raw_metadata"]["path"] == "https://signed.example/report"

    ai_report = next(item.metadata for item in mapped.reports if item.report_type == "aiReport")
    assert ai_report["ai_confidence"] == 0
    assert ai_report["number_of_heatmap_images"] == 0
    assert ai_report["gma_left_eye_cdr"] == 0.0
    assert ai_report["gma_right_eye_cdr"] == 0.0


def test_map_exam_payload_maps_pristine_montage_and_doctor_report():
    mapped = map_exam_payload(
        {
            "patientDetails": {"id": 1, "mrn": "556899", "gender": "MALE", "siteId": 5504695309172736},
            "examDetails": {
                "id": 2,
                "localId": "PRI5-2140::1768280217",
                "examDate": 1768280217456,
                "examState": "GRADED",
                "deviceType": ["PRISTINE"],
                "medicalHistory": "",
                "reportDate": 1768282149634,
            },
            "images": {
                "pristineImages": {
                    "EDITED": [
                        {
                            "id": 3,
                            "localId": "E1768282125.5546598",
                            "examId": 2,
                            "date": 1768282125554,
                            "deviceType": "PRISTINE",
                            "laterality": "LEFT",
                            "editOperations": ["MONTAGE"],
                            "originalImageIds": [10, 11],
                            "width": 5067,
                            "height": 6838,
                        }
                    ]
                }
            },
            "report": {
                "id": 4,
                "examId": 2,
                "patientId": 1,
                "localId": "PRI5-2140::1768280217-report",
                "reportDate": 1768282149634,
                "path": "https://signed.example/report",
                "imageIds": [3],
                "referRequired": False,
                "leftEyeDiagnosis": {"diagnoses": ["NA"], "comments": ""},
                "rightEyeDiagnosis": {"diagnoses": ["NA"], "comments": ""},
            },
        }
    )

    assert mapped.encounter["device_type"] == "PRISTINE"
    assert mapped.encounter["has_doctor_report"] is True
    image = mapped.images[0].metadata
    assert image["laterality"] == "OS"
    assert image["is_montage"] is True
    assert image["original_remidio_image_ids"] == [10, 11]
    report = mapped.reports[0].metadata
    assert report["remidio_report_type"] == "doctor_report"
    assert report["linked_remidio_image_ids"] == [3]
    assert report["left_eye_diagnosis"] == ["NA"]
