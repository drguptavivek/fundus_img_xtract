"""Map Remidio gateway payloads into EncounterSet metadata values.

This module is intentionally persistence-free. The future save/upsert service
should call this mapper, then perform duplicate-safe writes against local
EncounterSet storage.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class RemidioMappedImage:
    source_image_id: str | None
    metadata: dict[str, Any]


@dataclass(frozen=True)
class RemidioMappedReport:
    source_report_id: str | None
    report_type: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class RemidioEncounterMetadataMap:
    patient: dict[str, Any]
    encounter: dict[str, Any]
    images: list[RemidioMappedImage]
    reports: list[RemidioMappedReport]


def map_exam_payload(
    payload: dict[str, Any],
    *,
    site_custom_identifier: str | None = None,
) -> RemidioEncounterMetadataMap:
    """Map one Remidio exam object to EncounterSet metadata dictionaries."""
    patient_details = _dict(payload.get("patientDetails"))
    exam_details = _dict(payload.get("examDetails"))
    images = _dict(payload.get("images"))

    patient = {
        "hospital_UHID": _str(patient_details.get("mrn")),
        "remidio_patient_id": _str(patient_details.get("id")),
        "patient_name": _join_name(patient_details.get("firstName"), patient_details.get("lastName")),
        "patient_dob": _ms_to_date(patient_details.get("dateOfBirth")),
        "patient_age_yrs": _age_years(patient_details.get("dateOfBirth"), exam_details.get("examDate")),
        "sex": _normalize_sex(patient_details.get("gender")),
        "remidio_site_id": _str(patient_details.get("siteId")),
        "remidio_site_custom_identifier": site_custom_identifier,
        "remidio_patient_raw_metadata": _source_json(patient_details),
    }

    encounter = {
        "remidio_exam_id": _str(exam_details.get("id")),
        "remidio_exam_local_id": _str(exam_details.get("localId")),
        "exam_code": _str(exam_details.get("examCustomId")),
        "capture_datetime": _ms_to_datetime(exam_details.get("examDate")),
        "remidio_exam_report_datetime": _ms_to_datetime(exam_details.get("reportDate")),
        "device_type": _first_or_join(exam_details.get("deviceType")),
        "exam_state": _str(exam_details.get("examState")),
        "medical_history": _str(exam_details.get("medicalHistory")),
        "has_doctor_report": isinstance(payload.get("report"), dict),
        "has_ai_report": isinstance(payload.get("aiReport"), dict),
        "has_gma_report": isinstance(payload.get("gmaReport"), dict),
        "has_medios_ai_report": isinstance(payload.get("mediosAIReport"), dict),
        "clinical_image_count": _count_images(images),
        "report_document_count": _count_reports(payload),
        "remidio_encounter_raw_metadata": _source_json(_encounter_source_payload(payload)),
    }

    mapped_images = _map_images(images)
    mapped_reports = _map_reports(payload)
    return RemidioEncounterMetadataMap(
        patient=_drop_empty(patient),
        encounter=_drop_empty(encounter),
        images=mapped_images,
        reports=mapped_reports,
    )


def _map_images(images: dict[str, Any]) -> list[RemidioMappedImage]:
    mapped: list[RemidioMappedImage] = []
    for bucket_name, bucket in images.items():
        for variant_name, rows in _dict(bucket).items():
            if not isinstance(rows, list):
                continue
            for row in rows:
                image = _dict(row)
                disc_quality = _dict(image.get("discQualityResults"))
                edit_operations = image.get("editOperations")
                metadata = {
                    "remidio_image_id": _str(image.get("id")),
                    "remidio_image_local_id": _str(image.get("localId")),
                    "remidio_image_exam_id": _str(image.get("examId")),
                    "image_bucket": bucket_name,
                    "image_variant": variant_name,
                    "image_capture_datetime": _ms_to_datetime(image.get("date")),
                    "image_device_type": _str(image.get("deviceType")),
                    "laterality": _normalize_laterality(image.get("laterality")),
                    "fundus_field": _str(image.get("field")),
                    "image_segment": _str(image.get("imageSegment")),
                    "remidio_image_quality": _str(image.get("quality")),
                    "is_cropped": image.get("isCropped") if isinstance(image.get("isCropped"), bool) else None,
                    "is_montage": "MONTAGE" in edit_operations if isinstance(edit_operations, list) else None,
                    "edit_operations": edit_operations if isinstance(edit_operations, list) else None,
                    "original_remidio_image_ids": image.get("originalImageIds") if isinstance(image.get("originalImageIds"), list) else None,
                    "width_px": _int(image.get("width")),
                    "height_px": _int(image.get("height")),
                    "source_path_present": bool(image.get("path")),
                    "thumbnail_path_present": bool(image.get("thumbnailPath")),
                    "disc_present": disc_quality.get("discPresent") if isinstance(disc_quality.get("discPresent"), bool) else None,
                    "disc_quality_acceptable": disc_quality.get("acceptableQuality")
                    if isinstance(disc_quality.get("acceptableQuality"), bool)
                    else None,
                    "disc_quality_score": _number(disc_quality.get("qualityScore")),
                    "disc_roi_x": _number(disc_quality.get("roiX")),
                    "disc_roi_y": _number(disc_quality.get("roiY")),
                    "remidio_image_exif_metadata": _parse_json_string(image.get("metadata")),
                    "remidio_image_raw_metadata": _source_json(image),
                }
                mapped.append(RemidioMappedImage(source_image_id=_str(image.get("id")), metadata=_drop_empty(metadata)))
    return mapped


def _map_reports(payload: dict[str, Any]) -> list[RemidioMappedReport]:
    mapped: list[RemidioMappedReport] = []
    for report_type in ("report", "aiReport", "gmaReport", "mediosAIReport"):
        report = _dict(payload.get(report_type))
        if not report:
            continue
        left_eye = _dict(report.get("leftEyeDiagnosis"))
        right_eye = _dict(report.get("rightEyeDiagnosis"))
        dr_result = _dict(report.get("drResult"))
        gma_result = _dict(report.get("gmaResult"))
        metadata = {
            "remidio_report_id": _str(report.get("id")),
            "remidio_report_type": "doctor_report" if report_type == "report" else report_type,
            "remidio_report_exam_id": _str(report.get("examId")),
            "remidio_report_patient_id": _str(report.get("patientId")),
            "remidio_report_local_id": _str(report.get("localId")),
            "remidio_report_datetime": _ms_to_datetime(report.get("reportDate") or report.get("generatedDate")),
            "report_path_present": bool(report.get("path")),
            "linked_remidio_image_ids": report.get("imageIds") if isinstance(report.get("imageIds"), list) else None,
            "refer_required": report.get("referRequired") if isinstance(report.get("referRequired"), bool) else None,
            "left_eye_diagnosis": left_eye.get("diagnoses") if isinstance(left_eye.get("diagnoses"), list) else None,
            "left_eye_report_comments": _str(left_eye.get("comments")),
            "right_eye_diagnosis": right_eye.get("diagnoses") if isinstance(right_eye.get("diagnoses"), list) else None,
            "right_eye_report_comments": _str(right_eye.get("comments")),
            "reporting_doctor_id": _str(report.get("reportingDoctorId")),
            "ai_confidence": _number(_first_present(report.get("confidence"), dr_result.get("confidence"))),
            "ai_input_sufficient": _bool_or_none(report.get("inputSufficient"), dr_result.get("inputSufficient")),
            "ai_quality_sufficient": _bool_or_none(report.get("qualitySufficient"), dr_result.get("qualitySufficient")),
            "ai_suggested_refer": _bool_or_none(report.get("suggestedRefer"), dr_result.get("suggestedRefer")),
            "number_of_heatmap_images": _int(
                _first_present(report.get("numberOfHeatmapImages"), dr_result.get("numberOfHeatmapImages"))
            ),
            "gma_left_eye_cdr": _number(_first_present(report.get("leftEyeCdr"), gma_result.get("leftEyeCdr"))),
            "gma_right_eye_cdr": _number(_first_present(report.get("rightEyeCdr"), gma_result.get("rightEyeCdr"))),
            "gma_suggested_refer": _bool_or_none(gma_result.get("suggestedRefer"), report.get("suggestedRefer")),
            "gma_patient_level_result": _str(gma_result.get("patientLevelResult")),
            "remidio_report_raw_metadata": _source_json(report),
        }
        mapped.append(
            RemidioMappedReport(
                source_report_id=_str(report.get("id")),
                report_type=str(metadata["remidio_report_type"]),
                metadata=_drop_empty(metadata),
            )
        )
    return mapped


def _encounter_source_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in payload.items()
        if key not in {"patientDetails", "images", "report", "aiReport", "gmaReport", "mediosAIReport"}
    }


def _count_images(images: dict[str, Any]) -> int:
    count = 0
    for bucket in images.values():
        for rows in _dict(bucket).values():
            if isinstance(rows, list):
                count += len(rows)
    return count


def _count_reports(payload: dict[str, Any]) -> int:
    return sum(1 for key in ("report", "aiReport", "gmaReport", "mediosAIReport") if isinstance(payload.get(key), dict))


def _drop_empty(values: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value not in (None, "", [], {})}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bool_or_none(*values: Any) -> bool | None:
    for value in values:
        if isinstance(value, bool):
            return value
    return None


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def _first_or_join(value: Any) -> str | None:
    if isinstance(value, list):
        items = [str(item).strip() for item in value if str(item).strip()]
        return ",".join(items) if len(items) > 1 else (items[0] if items else None)
    return _str(value)


def _normalize_sex(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    if text in {"m", "male"}:
        return "male"
    if text in {"f", "female"}:
        return "female"
    if text in {"other", "unknown"}:
        return text
    return "unknown" if text else None


def _normalize_laterality(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    if text in {"RIGHT", "OD"}:
        return "OD"
    if text in {"LEFT", "OS"}:
        return "OS"
    if text in {"BOTH", "OU"}:
        return "OU"
    return "unknown" if text else None


def _join_name(first_name: Any, last_name: Any) -> str | None:
    parts = [str(value).strip() for value in (first_name, last_name) if str(value or "").strip()]
    return " ".join(parts) or None


def _ms_to_datetime(value: Any) -> str | None:
    ms = _int(value)
    if not ms:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def _ms_to_date(value: Any) -> str | None:
    timestamp = _ms_to_datetime(value)
    return timestamp[:10] if timestamp else None


def _age_years(dob_ms: Any, reference_ms: Any) -> int | None:
    dob_int = _int(dob_ms)
    ref_int = _int(reference_ms)
    if dob_int is None or ref_int is None:
        return None
    dob = datetime.fromtimestamp(dob_int / 1000, tz=timezone.utc).date()
    ref = datetime.fromtimestamp(ref_int / 1000, tz=timezone.utc).date()
    years = ref.year - dob.year - ((ref.month, ref.day) < (dob.month, dob.day))
    return years if years >= 0 else None


def _parse_json_string(value: Any) -> Any:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return {"_unparsed": value}


def _source_json(value: Any) -> Any:
    """Return source payload metadata unmodified for controlled DB storage."""
    return value
