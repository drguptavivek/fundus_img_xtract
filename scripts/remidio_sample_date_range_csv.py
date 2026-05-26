"""Export Remidio date-range examination samples into four CSVs.

This is a discovery helper for EncounterSet metadata planning. It reads the
encrypted RemidioConnection from the application database, calls
getExamsByDate, and writes patient, encounter, image, and report CSVs under
REMIDIO_Samples.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db_transaction_manager import transaction_scope
from models import RemidioConnection
from remidio_api_integration.client import RemidioClient
from remidio_api_integration.service import _secrets
from remidio_api_integration.validation import normalize_date, require_list_data


DEFAULT_OUTPUT_DIR = Path("REMIDIO_Samples")
URL_KEYS = {"path", "thumbnailPath", "url", "downloadUrl", "downloadURL", "signedUrl", "signedURL"}


def main() -> int:
    args = parse_args()
    start_date = normalize_date(args.start_date)
    end_date = normalize_date(args.end_date)
    sample_dir = args.output_dir / f"date_range_{safe_slug(args.site_custom_id)}_{start_date.replace('-', '')}_{end_date.replace('-', '')}"
    sample_dir.mkdir(parents=True, exist_ok=True)

    with transaction_scope() as db:
        connection = (
            db.query(RemidioConnection)
            .filter(RemidioConnection.name == args.connection_name)
            .one_or_none()
        )
        if connection is None:
            raise SystemExit(f"Remidio connection not found: {args.connection_name}")
        secrets = _secrets(connection)

    client = RemidioClient(secrets)
    payload = client.get_exams_by_date(
        start_date=start_date,
        end_date=end_date,
        site_custom_identifier=args.site_custom_id,
        include_file_paths=True,
    )
    exams = require_list_data(payload)

    patients: list[dict[str, Any]] = []
    encounters: list[dict[str, Any]] = []
    images: list[dict[str, Any]] = []
    reports: list[dict[str, Any]] = []

    for exam in exams:
        if not isinstance(exam, dict):
            continue
        patient = as_dict(exam.get("patientDetails"))
        details = as_dict(exam.get("examDetails"))
        exam_id = value(details.get("id"))
        patient_id = value(patient.get("id"))

        patients.append(
            {
                "remidio_patient_id": patient_id,
                "remidio_exam_id": exam_id,
                "site_custom_identifier": args.site_custom_id,
                "site_id": value(patient.get("siteId")),
                "mrn": value(patient.get("mrn")),
                "first_name": value(patient.get("firstName")),
                "middle_name": value(patient.get("middleName")),
                "last_name": value(patient.get("lastName")),
                "mobile": value(patient.get("mobile")),
                "mobile_number": value(patient.get("mobileNumber")),
                "email": value(patient.get("email")),
                "employee_id": value(patient.get("employeeId")),
                "date_of_birth_ms": value(patient.get("dateOfBirth")),
                "date_of_birth_utc": ms_to_utc(patient.get("dateOfBirth")),
                "patient_age_years": value(age_years(patient.get("dateOfBirth"), details.get("examDate"))),
                "gender": value(patient.get("gender")),
                "patient_keys": json_list(sorted(patient.keys())),
            }
        )

        encounters.append(
            {
                "remidio_exam_id": exam_id,
                "remidio_patient_id": patient_id,
                "site_custom_identifier": args.site_custom_id,
                "exam_local_id": value(details.get("localId")),
                "exam_custom_id": value(details.get("examCustomId")),
                "exam_date_ms": value(details.get("examDate")),
                "exam_date_utc": ms_to_utc(details.get("examDate")),
                "report_date_ms": value(details.get("reportDate")),
                "report_date_utc": ms_to_utc(details.get("reportDate")),
                "device_types": json_list(details.get("deviceType")),
                "exam_state": value(details.get("examState")),
                "medical_history": value(details.get("medicalHistory")),
                "creating_user": value(exam.get("creatingUser")),
                "ordering_provider": value(exam.get("orderingProvider")),
                "reporting_doctor": value(exam.get("reportingDoctor")),
                "doctor_report_present": isinstance(exam.get("report"), dict),
                "ai_report_present": isinstance(exam.get("aiReport"), dict),
                "gma_report_present": isinstance(exam.get("gmaReport"), dict),
                "medios_ai_report_present": isinstance(exam.get("mediosAIReport"), dict),
                "exam_detail_keys": json_list(sorted(details.keys())),
                "exam_keys": json_list(sorted(exam.keys())),
            }
        )

        images.extend(image_rows(exam, exam_id=exam_id, patient_id=patient_id))
        reports.extend(report_rows(exam, exam_id=exam_id, patient_id=patient_id))

    manifest = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "connection_name": args.connection_name,
        "site_custom_identifier": args.site_custom_id,
        "start_date": start_date,
        "end_date": end_date,
        "exam_count": len(exams),
        "patient_rows": len(patients),
        "encounter_rows": len(encounters),
        "image_rows": len(images),
        "report_rows": len(reports),
    }

    write_csv(sample_dir / "patients.csv", patients)
    write_csv(sample_dir / "encounters.csv", encounters)
    write_csv(sample_dir / "images.csv", images)
    write_csv(sample_dir / "reports.csv", reports)
    (sample_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    print(json.dumps({"output_dir": str(sample_dir), **manifest}, indent=2, sort_keys=True))
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--connection-name", default="r.pcenter")
    parser.add_argument("--site-custom-id", default="rpc_comoph_2")
    parser.add_argument("--start-date", required=True, help="DD-MM-YYYY or YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="DD-MM-YYYY or YYYY-MM-DD")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def image_rows(exam: dict[str, Any], *, exam_id: str, patient_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    images = as_dict(exam.get("images"))
    for bucket_name, bucket in images.items():
        bucket_dict = as_dict(bucket)
        for variant_name, items in bucket_dict.items():
            if not isinstance(items, list):
                continue
            for item in items:
                image = as_dict(item)
                if not image:
                    continue
                disc_quality = as_dict(image.get("discQualityResults"))
                rows.append(
                    {
                        "remidio_exam_id": exam_id,
                        "remidio_patient_id": patient_id,
                        "remidio_image_id": value(image.get("id")),
                        "image_local_id": value(image.get("localId")),
                        "image_bucket": bucket_name,
                        "image_variant": variant_name,
                        "image_date_ms": value(image.get("date")),
                        "image_date_utc": ms_to_utc(image.get("date")),
                        "device_type": value(image.get("deviceType")),
                        "laterality": value(image.get("laterality")),
                        "field": value(image.get("field")),
                        "image_segment": value(image.get("imageSegment")),
                        "quality": value(image.get("quality")),
                        "is_cropped": value(image.get("isCropped")),
                        "width": value(image.get("width")),
                        "height": value(image.get("height")),
                        "edit_operations": json_list(image.get("editOperations")),
                        "original_image_ids": json_list(image.get("originalImageIds")),
                        "path_present": bool(image.get("path")),
                        "thumbnail_path_present": bool(image.get("thumbnailPath")),
                        "metadata_present": bool(image.get("metadata")),
                        "metadata_keys": metadata_keys(image.get("metadata")),
                        "disc_quality_acceptable": value(disc_quality.get("acceptableQuality")),
                        "disc_present": value(disc_quality.get("discPresent")),
                        "disc_quality_score": value(disc_quality.get("qualityScore")),
                        "disc_roi_x": value(disc_quality.get("roiX")),
                        "disc_roi_y": value(disc_quality.get("roiY")),
                        "image_keys": json_list(sorted(image.keys())),
                    }
                )
    return rows


def report_rows(exam: dict[str, Any], *, exam_id: str, patient_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, raw_report in exam.items():
        if key == "images":
            continue
        if isinstance(raw_report, dict) and key.lower().endswith("report"):
            rows.append(report_row(key, raw_report, exam_id=exam_id, patient_id=patient_id))
    return rows


def report_row(report_type: str, report: dict[str, Any], *, exam_id: str, patient_id: str) -> dict[str, Any]:
    left_diag = as_dict(report.get("leftEyeDiagnosis"))
    right_diag = as_dict(report.get("rightEyeDiagnosis"))
    dr_result = as_dict(report.get("drResult"))
    gma_result = as_dict(report.get("gmaResult"))
    return {
        "remidio_exam_id": exam_id,
        "remidio_patient_id": patient_id,
        "report_type": report_type,
        "remidio_report_id": value(report.get("id")),
        "report_exam_id": value(report.get("examId")),
        "report_patient_id": value(report.get("patientId")),
        "report_local_id": value(report.get("localId")),
        "generated_date_ms": value(first_present(report.get("generatedDate"), report.get("reportDate"))),
        "generated_date_utc": ms_to_utc(first_present(report.get("generatedDate"), report.get("reportDate"))),
        "path_present": bool(report.get("path")),
        "image_ids": json_list(report.get("imageIds")),
        "refer_required": value(report.get("referRequired")),
        "suggested_refer": value(report.get("suggestedRefer")),
        "reporting_doctor_id": value(report.get("reportingDoctorId")),
        "left_eye_diagnoses": json_list(left_diag.get("diagnoses")),
        "left_eye_comments": value(left_diag.get("comments")),
        "right_eye_diagnoses": json_list(right_diag.get("diagnoses")),
        "right_eye_comments": value(right_diag.get("comments")),
        "confidence": value(first_present(report.get("confidence"), dr_result.get("confidence"))),
        "input_sufficient": value(report.get("inputSufficient") if "inputSufficient" in report else dr_result.get("inputSufficient")),
        "quality_sufficient": value(report.get("qualitySufficient") if "qualitySufficient" in report else dr_result.get("qualitySufficient")),
        "number_of_heatmap_images": value(first_present(report.get("numberOfHeatmapImages"), dr_result.get("numberOfHeatmapImages"))),
        "left_eye_cdr": value(first_present(report.get("leftEyeCdr"), gma_result.get("leftEyeCdr"))),
        "right_eye_cdr": value(first_present(report.get("rightEyeCdr"), gma_result.get("rightEyeCdr"))),
        "patient_level_result": value(gma_result.get("patientLevelResult")),
        "report_keys": json_list(sorted(report.keys())),
        "dr_result_keys": json_list(sorted(dr_result.keys())),
        "gma_result_keys": json_list(sorted(gma_result.keys())),
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames: list[str] = []
    for row in rows:
        for key in row.keys():
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def value(item: Any) -> str:
    if item is None:
        return ""
    if isinstance(item, (dict, list)):
        return json.dumps(redact_urls(item), sort_keys=True)
    return str(item)


def json_list(item: Any) -> str:
    if item is None or item == "":
        return "[]"
    if not isinstance(item, list):
        item = [item]
    return json.dumps(redact_urls(item), sort_keys=True)


def metadata_keys(item: Any) -> str:
    if not isinstance(item, str) or not item.strip():
        return "[]"
    try:
        parsed = json.loads(item)
    except json.JSONDecodeError:
        return json.dumps(["<invalid-json>"])
    if not isinstance(parsed, dict):
        return "[]"
    return json.dumps(sorted(parsed.keys()))


def redact_urls(item: Any) -> Any:
    if isinstance(item, dict):
        return {key: ("[redacted-url]" if key in URL_KEYS else redact_urls(val)) for key, val in item.items()}
    if isinstance(item, list):
        return [redact_urls(val) for val in item]
    return item


def first_present(*items: Any) -> Any:
    for item in items:
        if item is not None and item != "":
            return item
    return None


def age_years(dob_item: Any, reference_item: Any) -> int | None:
    try:
        dob_ms = int(dob_item)
        reference_ms = int(reference_item)
    except (TypeError, ValueError):
        return None
    dob = datetime.fromtimestamp(dob_ms / 1000, tz=timezone.utc).date()
    reference = datetime.fromtimestamp(reference_ms / 1000, tz=timezone.utc).date()
    years = reference.year - dob.year - ((reference.month, reference.day) < (dob.month, dob.day))
    return years if years >= 0 else None


def ms_to_utc(item: Any) -> str:
    try:
        ms = int(item)
    except (TypeError, ValueError):
        return ""
    if ms == 0:
        return ""
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def safe_slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._") or "sample"


if __name__ == "__main__":
    raise SystemExit(main())
