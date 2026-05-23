"""Validate fresh Remidio samples against mapper output and metadata schema.

This discovery helper fetches Remidio exams for a date range, maps them through
the EncounterSet metadata mapper, and writes a full local validation summary
under REMIDIO_Samples. It preserves patient/source values needed for schema
analysis, but redacts signed URL values because those are credentials.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db_transaction_manager import transaction_scope
from models import RemidioConnection
from remidio_api_integration.client import RemidioClient
from remidio_api_integration.mapper import map_exam_payload
from remidio_api_integration.service import _secrets
from remidio_api_integration.validation import normalize_date, require_list_data


DEFAULT_OUTPUT_DIR = Path("REMIDIO_Samples")
SIGNED_URL_KEYS = {"signedUrl", "signedURL"}
MIGRATION_PATH = PROJECT_ROOT / "migrations/versions/e0f1a2b3c4d5_seed_remidio_metadata_and_encounter_set.py"
CORE_FIELDS_PATH = PROJECT_ROOT / "migrations/versions/e4f3a2b1c0d9_seed_core_upload_metadata_fields.py"


MAPPED_SOURCE_PATHS = {
    "patientDetails.mrn",
    "patientDetails.id",
    "patientDetails.firstName",
    "patientDetails.lastName",
    "patientDetails.dateOfBirth",
    "patientDetails.gender",
    "patientDetails.siteId",
    "examDetails.id",
    "examDetails.localId",
    "examDetails.examCustomId",
    "examDetails.examDate",
    "examDetails.reportDate",
    "examDetails.deviceType",
    "examDetails.examState",
    "examDetails.medicalHistory",
    "images.*.*.id",
    "images.*.*.localId",
    "images.*.*.examId",
    "images.*.*.date",
    "images.*.*.deviceType",
    "images.*.*.laterality",
    "images.*.*.field",
    "images.*.*.imageSegment",
    "images.*.*.quality",
    "images.*.*.isCropped",
    "images.*.*.editOperations",
    "images.*.*.originalImageIds",
    "images.*.*.width",
    "images.*.*.height",
    "images.*.*.path",
    "images.*.*.thumbnailPath",
    "images.*.*.discQualityResults.discPresent",
    "images.*.*.discQualityResults.acceptableQuality",
    "images.*.*.discQualityResults.qualityScore",
    "images.*.*.discQualityResults.roiX",
    "images.*.*.discQualityResults.roiY",
    "images.*.*.metadata",
    "*.id",
    "*.examId",
    "*.patientId",
    "*.localId",
    "*.reportDate",
    "*.generatedDate",
    "*.path",
    "*.imageIds",
    "*.referRequired",
    "*.leftEyeDiagnosis.diagnoses",
    "*.leftEyeDiagnosis.comments",
    "*.rightEyeDiagnosis.diagnoses",
    "*.rightEyeDiagnosis.comments",
    "*.reportingDoctorId",
    "*.confidence",
    "*.inputSufficient",
    "*.qualitySufficient",
    "*.suggestedRefer",
    "*.numberOfHeatmapImages",
    "*.leftEyeCdr",
    "*.rightEyeCdr",
    "*.drResult.confidence",
    "*.drResult.inputSufficient",
    "*.drResult.qualitySufficient",
    "*.drResult.suggestedRefer",
    "*.drResult.numberOfHeatmapImages",
    "*.gmaResult.leftEyeCdr",
    "*.gmaResult.rightEyeCdr",
    "*.gmaResult.suggestedRefer",
    "*.gmaResult.patientLevelResult",
}
RAW_CATCHALL_SOURCE_PATHS = {
    "creatingUser",
    "orderingProvider",
    "previousReports",
    "reportingDoctor",
}


@dataclass
class FieldStats:
    count: int = 0
    values: Counter[str] = field(default_factory=Counter)
    types: Counter[str] = field(default_factory=Counter)
    examples: list[Any] = field(default_factory=list)

    def observe(self, value: Any) -> None:
        self.count += 1
        self.types[type_label(value)] += 1
        if len(self.examples) < 8:
            self.examples.append(url_redacted(value))
        value_key = stable_value(value)
        if len(self.values) < 100 or value_key in self.values:
            self.values[value_key] += 1


def main() -> int:
    args = parse_args()
    start_date, end_date = parse_date_range(args.start_date, args.end_date)

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
    )
    exams = [exam for exam in require_list_data(payload) if isinstance(exam, dict)]
    contract = load_contract()
    result = validate_exams(
        exams,
        field_contract=contract["fields"],
        schema_keys=contract["schema_keys"],
        site_custom_identifier=args.site_custom_id,
    )
    output_dir = (
        args.output_dir
        / f"validation_{safe_slug(args.site_custom_id)}_{start_date.replace('-', '')}_{end_date.replace('-', '')}"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    summary = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "connection_name": args.connection_name,
        "site_custom_identifier": args.site_custom_id,
        "start_date": start_date,
        "end_date": end_date,
        "notes": [
            "This local validation summary preserves source patient values for schema analysis.",
            "Signed URL values are redacted because they are credentials, not metadata.",
            "REMIDIO_Samples is gitignored and this artifact must not be committed.",
        ],
        **result,
    }
    summary_path = output_dir / "mapping_validation_full.json"
    report_path = output_dir / "mapping_validation_full.md"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True, default=str), encoding="utf-8")
    report_path.write_text(render_markdown(summary), encoding="utf-8")
    print(json.dumps({"output_dir": str(output_dir), "json": str(summary_path), "markdown": str(report_path), **summary["counts"]}, indent=2, sort_keys=True))
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--connection-name", default="r.pcenter")
    parser.add_argument("--site-custom-id", default="rpc_comoph_2")
    parser.add_argument("--start-date", required=True, help="DD-MM-YYYY or YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="DD-MM-YYYY or YYYY-MM-DD")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def parse_date_range(start_date: str, end_date: str) -> tuple[str, str]:
    start = normalize_date(start_date)
    end = normalize_date(end_date)
    if datetime.strptime(end, "%d-%m-%Y") < datetime.strptime(start, "%d-%m-%Y"):
        raise SystemExit("Invalid date range: --start-date must be <= --end-date")
    return start, end


def load_contract() -> dict[str, Any]:
    remidio = load_module(MIGRATION_PATH, "remidio_metadata_contract")
    core = load_module(CORE_FIELDS_PATH, "core_metadata_contract")
    remidio_fields = _extract_contract_rows(remidio, "REMEDIO_FIELDS", "remidio")
    core_fields = _extract_contract_rows(core, "FIELDS", "core")
    fields: dict[str, dict[str, Any]] = {}
    for row in [*core_fields, *remidio_fields]:
        key = row.get("key")
        if not isinstance(key, str) or not key.strip():
            continue
        fields[key] = normalize_field_contract(row)
    schema_keys = getattr(remidio, "SCHEMA_KEYS", [])
    if not isinstance(schema_keys, list):
        schema_keys = list(schema_keys) if schema_keys is not None else []
    if not fields:
        raise RuntimeError("No valid metadata contract fields loaded.")
    return {"fields": fields, "schema_keys": schema_keys}


def _extract_contract_rows(module: Any, attr: str, contract_name: str) -> list[dict[str, Any]]:
    rows = getattr(module, attr, None)
    if not isinstance(rows, list):
        raise RuntimeError(f"Missing {contract_name} contract rows: expected list in {attr}")
    return [row for row in rows if isinstance(row, dict)]


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load migration module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def normalize_field_contract(row: dict[str, Any]) -> dict[str, Any]:
    field_type = row.get("field_type")
    if not isinstance(field_type, str):
        field_type = "text"
    selection_mode = row.get("selection_mode")
    options = row.get("options_json")
    if not isinstance(options, list):
        options = []
    return {
        "scope": row.get("scope"),
        "key": row["key"],
        "label": row.get("label"),
        "type": field_type,
        "selection_mode": selection_mode,
        "options": options,
        "required_at_upload_default": bool(row.get("required_at_upload_default", False)),
        "required_for_verification_default": bool(row.get("required_for_verification_default", False)),
        "visible_to_grader_default": bool(row.get("visible_to_grader_default", False)),
        "is_pii_default": bool(row.get("is_pii_default", False)),
    }


def validate_exams(
    exams: list[dict[str, Any]],
    *,
    field_contract: dict[str, dict[str, Any]],
    schema_keys: list[str],
    site_custom_identifier: str,
) -> dict[str, Any]:
    mapped_stats: dict[str, dict[str, FieldStats]] = {
        "patient": defaultdict(FieldStats),
        "encounter": defaultdict(FieldStats),
        "image": defaultdict(FieldStats),
        "document": defaultdict(FieldStats),
    }
    source_stats: dict[str, FieldStats] = defaultdict(FieldStats)
    type_mismatches: list[dict[str, Any]] = []
    select_mismatches: list[dict[str, Any]] = []
    missing_required: list[dict[str, Any]] = []
    mapper_errors: list[dict[str, Any]] = []
    image_bucket_counts: Counter[str] = Counter()
    image_variant_counts: Counter[str] = Counter()
    report_type_counts: Counter[str] = Counter()
    device_type_counts: Counter[str] = Counter()
    exam_state_counts: Counter[str] = Counter()
    sample_exams: list[dict[str, Any]] = []
    mapped_counts = Counter()

    for exam_index, exam in enumerate(exams, start=1):
        observe_source(source_stats, exam)
        details = as_dict(exam.get("examDetails"))
        patient = as_dict(exam.get("patientDetails"))
        exam_id = string_or_none(details.get("id"))
        patient_id = string_or_none(patient.get("id"))
        if len(sample_exams) < 12:
            sample_exams.append(source_sample(exam, exam_index=exam_index))
        for device_type in list_value(details.get("deviceType")):
            device_type_counts[str(device_type)] += 1
        if details.get("examState") is not None:
            exam_state_counts[str(details.get("examState"))] += 1
        for bucket_name, bucket in as_dict(exam.get("images")).items():
            for variant_name, rows in as_dict(bucket).items():
                if isinstance(rows, list):
                    image_bucket_counts[str(bucket_name)] += len(rows)
                    image_variant_counts[str(variant_name)] += len(rows)
        for key, value in exam.items():
            if key != "images" and isinstance(value, dict) and key.lower().endswith("report"):
                report_type_counts["doctor_report" if key == "report" else key] += 1

        try:
            mapped = map_exam_payload(exam, site_custom_identifier=site_custom_identifier)
        except (AttributeError, IndexError, KeyError, RuntimeError, TypeError, ValueError) as exc:
            mapper_errors.append({"exam_index": exam_index, "exam_id": exam_id, "patient_id": patient_id, "error": str(exc)})
            continue

        observe_mapped_scope(
            mapped.patient,
            "patient",
            mapped_stats,
            field_contract,
            type_mismatches,
            select_mismatches,
            missing_required,
            exam_index=exam_index,
            exam_id=exam_id,
            patient_id=patient_id,
        )
        observe_mapped_scope(
            mapped.encounter,
            "encounter",
            mapped_stats,
            field_contract,
            type_mismatches,
            select_mismatches,
            missing_required,
            exam_index=exam_index,
            exam_id=exam_id,
            patient_id=patient_id,
        )
        for image in mapped.images:
            mapped_counts["images"] += 1
            observe_mapped_scope(
                image.metadata,
                "image",
                mapped_stats,
                field_contract,
                type_mismatches,
                select_mismatches,
                missing_required,
                exam_index=exam_index,
                exam_id=exam_id,
                patient_id=patient_id,
                source_id=image.source_image_id,
            )
        for report in mapped.reports:
            mapped_counts["reports"] += 1
            observe_mapped_scope(
                report.metadata,
                "document",
                mapped_stats,
                field_contract,
                type_mismatches,
                select_mismatches,
                missing_required,
                exam_index=exam_index,
                exam_id=exam_id,
                patient_id=patient_id,
                source_id=report.source_report_id,
            )

    mapped_keys = {scope: sorted(stats.keys()) for scope, stats in mapped_stats.items()}
    schema_key_set = set(schema_keys)
    mapped_key_set = {key for stats in mapped_keys.values() for key in stats}
    source_paths = summarize_stats(source_stats)
    raw_catchall_source_paths = {
        path: stats
        for path, stats in source_paths.items()
        if source_path_is_raw_catchall(path)
    }
    unmapped_source_paths = {
        path: stats
        for path, stats in source_paths.items()
        if not source_path_is_known_mapped(path) and not source_path_is_raw_catchall(path)
    }
    return {
        "counts": {
            "exam_count": len(exams),
            "mapped_image_count": mapped_counts["images"],
            "mapped_report_count": mapped_counts["reports"],
            "source_image_count": sum(image_bucket_counts.values()),
            "source_report_count": sum(report_type_counts.values()),
            "mapper_error_count": len(mapper_errors),
            "type_mismatch_count": len(type_mismatches),
            "select_mismatch_count": len(select_mismatches),
            "missing_required_count": len(missing_required),
            "mapped_keys_missing_from_schema_count": len(mapped_key_set - schema_key_set),
            "schema_keys_never_observed_in_mapped_output_count": len(schema_key_set - mapped_key_set),
            "source_paths_preserved_in_raw_catchall_count": len(raw_catchall_source_paths),
            "unmapped_observed_source_path_count": len(unmapped_source_paths),
        },
        "source_distribution": {
            "device_types": dict(device_type_counts),
            "exam_states": dict(exam_state_counts),
            "image_buckets": dict(image_bucket_counts),
            "image_variants": dict(image_variant_counts),
            "report_types": dict(report_type_counts),
        },
        "mapped_key_coverage": {
            "schema_keys": schema_keys,
            "mapped_keys_by_scope": mapped_keys,
            "mapped_keys_missing_from_schema": sorted(mapped_key_set - schema_key_set),
            "schema_keys_never_observed_in_mapped_output": sorted(schema_key_set - mapped_key_set),
        },
        "inconsistencies": {
            "mapper_errors": mapper_errors,
            "type_mismatches": type_mismatches[:500],
            "select_mismatches": select_mismatches[:500],
            "missing_required_values": missing_required[:500],
            "source_paths_preserved_in_raw_catchall": raw_catchall_source_paths,
            "unmapped_observed_source_paths": unmapped_source_paths,
        },
        "mapped_value_profile": {
            scope: summarize_stats(stats)
            for scope, stats in mapped_stats.items()
        },
        "source_value_profile": source_paths,
        "sample_exams": sample_exams,
    }


def observe_mapped_scope(
    values: dict[str, Any],
    scope: str,
    mapped_stats: dict[str, dict[str, FieldStats]],
    field_contract: dict[str, dict[str, Any]],
    type_mismatches: list[dict[str, Any]],
    select_mismatches: list[dict[str, Any]],
    missing_required: list[dict[str, Any]],
    *,
    exam_index: int,
    exam_id: str | None,
    patient_id: str | None,
    source_id: str | None = None,
) -> None:
    for key, value in values.items():
        mapped_stats[scope][key].observe(value)
        contract = field_contract.get(key)
        if contract is None:
            continue
        if contract["scope"] != scope:
            type_mismatches.append(issue("scope", key, value, contract, exam_index, exam_id, patient_id, source_id, observed_scope=scope))
        if not value_matches_type(value, contract["type"]):
            type_mismatches.append(issue("type", key, value, contract, exam_index, exam_id, patient_id, source_id, observed_type=type_label(value)))
        if contract["type"] == "select":
            option_values = {str(option.get("value")) for option in contract["options"] if isinstance(option, dict)}
            if value is not None and str(value) not in option_values:
                select_mismatches.append(issue("select_option", key, value, contract, exam_index, exam_id, patient_id, source_id, allowed_values=sorted(option_values)))
    for key, contract in field_contract.items():
        if contract["scope"] != scope or not contract.get("required_for_verification_default"):
            continue
        if key in values:
            continue
        missing_required.append(
            {
                "scope": scope,
                "key": key,
                "exam_index": exam_index,
                "exam_id": exam_id,
                "patient_id": patient_id,
                "source_id": source_id,
                "reason": "required_for_verification_default but mapper emitted no value",
            }
        )


def observe_source(source_stats: dict[str, FieldStats], exam: dict[str, Any]) -> None:
    for path, value in flatten_source(exam):
        source_stats[path].observe(value)


def flatten_source(exam: dict[str, Any]) -> list[tuple[str, Any]]:
    rows: list[tuple[str, Any]] = []
    for key, value in exam.items():
        if key == "images":
            for bucket_name, bucket in as_dict(value).items():
                for variant_name, items in as_dict(bucket).items():
                    if not isinstance(items, list):
                        continue
                    for item in items:
                        flatten_object(as_dict(item), f"images.{bucket_name}.{variant_name}", rows)
            continue
        if isinstance(value, dict) and key.lower().endswith("report"):
            flatten_object(value, key, rows)
            continue
        if key in {"patientDetails", "examDetails"} and isinstance(value, dict):
            flatten_object(value, key, rows)
            continue
        if key not in {"patientDetails", "examDetails", "images"}:
            rows.append((key, value))
    return rows


def flatten_object(value: dict[str, Any], prefix: str, rows: list[tuple[str, Any]]) -> None:
    for key, item in value.items():
        path = f"{prefix}.{key}"
        if isinstance(item, dict):
            flatten_object(item, path, rows)
        else:
            rows.append((path, item))


def source_sample(exam: dict[str, Any], *, exam_index: int) -> dict[str, Any]:
    details = as_dict(exam.get("examDetails"))
    patient = as_dict(exam.get("patientDetails"))
    reports = [key for key, value in exam.items() if key != "images" and isinstance(value, dict) and key.lower().endswith("report")]
    images = []
    for bucket_name, bucket in as_dict(exam.get("images")).items():
        for variant_name, items in as_dict(bucket).items():
            if not isinstance(items, list):
                continue
            for item in items[:3]:
                image = as_dict(item)
                images.append(
                    {
                        "bucket": bucket_name,
                        "variant": variant_name,
                        "id": image.get("id"),
                        "laterality": image.get("laterality"),
                        "field": image.get("field"),
                        "imageSegment": image.get("imageSegment"),
                        "quality": image.get("quality"),
                        "deviceType": image.get("deviceType"),
                    }
                )
    return {
        "exam_index": exam_index,
        "patientDetails": url_redacted(patient),
        "examDetails": url_redacted(details),
        "report_keys": reports,
        "image_examples": images[:8],
    }


def source_path_is_known_mapped(path: str) -> bool:
    normalized = re.sub(r"images\.[^.]+\.[^.]+", "images.*.*", path)
    if normalized in MAPPED_SOURCE_PATHS:
        return True
    report_normalized = re.sub(r"^(report|aiReport|gmaReport|mediosAIReport)\.", "*.", path)
    return report_normalized in MAPPED_SOURCE_PATHS


def source_path_is_raw_catchall(path: str) -> bool:
    return path in RAW_CATCHALL_SOURCE_PATHS


def issue(
    issue_type: str,
    key: str,
    value: Any,
    contract: dict[str, Any],
    exam_index: int,
    exam_id: str | None,
    patient_id: str | None,
    source_id: str | None,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "issue_type": issue_type,
        "scope": contract["scope"],
        "key": key,
        "expected_type": contract["type"],
        "value": url_redacted(value),
        "exam_index": exam_index,
        "exam_id": exam_id,
        "patient_id": patient_id,
        "source_id": source_id,
        **extra,
    }


def value_matches_type(value: Any, field_type: str) -> bool:
    if value is None:
        return True
    if field_type in {"text", "textarea", "date", "datetime", "phone", "email"}:
        return isinstance(value, str)
    if field_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if field_type == "decimal":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if field_type == "boolean":
        return isinstance(value, bool)
    if field_type == "select":
        return isinstance(value, str)
    if field_type == "json":
        return isinstance(value, (dict, list, str, int, float, bool))
    return True


def summarize_stats(stats: dict[str, FieldStats]) -> dict[str, Any]:
    return {
        key: {
            "count": value.count,
            "types": dict(value.types),
            "top_values": [
                {"value": decode_stable_value(item), "count": count}
                for item, count in value.values.most_common(20)
            ],
            "examples": value.examples,
        }
        for key, value in sorted(stats.items())
    }


def render_markdown(summary: dict[str, Any]) -> str:
    counts = summary["counts"]
    lines = [
        "# Remidio Mapping Validation Full Summary",
        "",
        f"- Captured at: `{summary['captured_at']}`",
        f"- Connection: `{summary['connection_name']}`",
        f"- Site custom identifier: `{summary['site_custom_identifier']}`",
        f"- Date range: `{summary['start_date']}` to `{summary['end_date']}`",
        f"- Exams: `{counts['exam_count']}`",
        f"- Source images / mapped images: `{counts['source_image_count']}` / `{counts['mapped_image_count']}`",
        f"- Source reports / mapped reports: `{counts['source_report_count']}` / `{counts['mapped_report_count']}`",
        "",
        "## Inconsistency Counts",
        "",
        f"- Mapper errors: `{counts['mapper_error_count']}`",
        f"- Type mismatches: `{counts['type_mismatch_count']}`",
        f"- Select-option mismatches: `{counts['select_mismatch_count']}`",
        f"- Missing required mapped values: `{counts['missing_required_count']}`",
        f"- Mapped keys missing from schema: `{counts['mapped_keys_missing_from_schema_count']}`",
        f"- Schema keys never observed in mapped output: `{counts['schema_keys_never_observed_in_mapped_output_count']}`",
        f"- Source paths preserved in raw catch-all: `{counts['source_paths_preserved_in_raw_catchall_count']}`",
        f"- Unmapped observed source paths: `{counts['unmapped_observed_source_path_count']}`",
        "",
        "## Source Distribution",
        "",
        "```json",
        json.dumps(summary["source_distribution"], indent=2, sort_keys=True),
        "```",
        "",
        "## Key Coverage",
        "",
        "```json",
        json.dumps(summary["mapped_key_coverage"], indent=2, sort_keys=True),
        "```",
        "",
        "## Inconsistencies",
        "",
        "```json",
        json.dumps(summary["inconsistencies"], indent=2, sort_keys=True),
        "```",
        "",
        "## Mapped Value Profile",
        "",
        "```json",
        json.dumps(summary["mapped_value_profile"], indent=2, sort_keys=True),
        "```",
        "",
        "## Source Value Profile",
        "",
        "```json",
        json.dumps(summary["source_value_profile"], indent=2, sort_keys=True),
        "```",
        "",
        "## Sample Exams",
        "",
        "```json",
        json.dumps(summary["sample_exams"], indent=2, sort_keys=True),
        "```",
        "",
    ]
    return "\n".join(lines)


def type_label(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "decimal"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    if value is None:
        return "null"
    return type(value).__name__


def stable_value(value: Any) -> str:
    return json.dumps(url_redacted(value), sort_keys=True, default=str)


def decode_stable_value(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def url_redacted(value: Any, *, key: str | None = None) -> Any:
    if isinstance(value, dict):
        return {str(item_key): url_redacted(item_value, key=str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [url_redacted(item, key=key) for item in value]
    if isinstance(value, str) and key is not None and _is_signed_url_key(key):
        return "[redacted-url]"
    return value


def _is_signed_url_key(key: str | None) -> bool:
    key_normalized = (key or "").replace("_", "").replace("-", "").lower()
    if not key_normalized:
        return False
    if key in SIGNED_URL_KEYS:
        return True
    return "signed" in key_normalized and "url" in key_normalized


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def list_value(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def safe_slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._") or "sample"


if __name__ == "__main__":
    raise SystemExit(main())
