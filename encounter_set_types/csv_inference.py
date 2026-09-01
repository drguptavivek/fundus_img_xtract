"""Privacy-safe CSV profiling for EncounterSetType configuration.

This module only produces a draft schema and mapping contract.  It never
persists CSV rows or creates clinical records.
"""
from __future__ import annotations

import csv
import hashlib
import io
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import PurePath
from typing import Any, BinaryIO


MAX_CSV_BYTES = 10 * 1024 * 1024
MAX_ROWS = 25_000
MAX_COLUMNS = 200
MAX_SELECT_OPTIONS = 30
MAX_OPTION_LENGTH = 255

_KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_EYE_SUFFIXES = {
    "od": "OD",
    "os": "OS",
    "rt": "OD",
    "lt": "OS",
    "re": "OD",
    "le": "OS",
}
_PAIR_FAMILIES = (("od", "os"), ("rt", "lt"), ("re", "le"))
_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".heic", ".dng", ".tif", ".tiff"}

_RESERVED_KEYS = {
    "instance_id": "encounter_identity",
    "submission_date": "capture_datetime",
}
_PATIENT_CANONICAL = {
    "age": "patient_age_yrs",
    "sex": "sex",
    "education": "education",
}
_ENCOUNTER_CANONICAL = {
    "source_project_id": "source_project_id",
    "form_id": "source_form_id",
    "source_form": "source_form",
    "state_code": "state_code",
    "state_name": "state_name",
    "district_code": "district_code",
    "district_name": "district_name",
    "keratoplasty_history_any_eye": "keratoplasty_history_any_eye",
}
_PII_KEYS = {"state_code", "state_name", "district_code", "district_name"}
_TYPE_OVERRIDES = {
    "source_project_id": "text",
    "source_form_id": "text",
    "state_code": "text",
    "district_code": "text",
    "co_cause_other": "textarea",
    "keratoplasty_barrier": "textarea",
    "co_treatment_barrier": "textarea",
}

_CANONICAL_MASTER_HINTS = {
    "patient_age_yrs": {"key": "patient_age_yrs", "scope": "patient", "type": "integer"},
    "sex": {"key": "sex", "scope": "patient", "type": "select"},
    "capture_datetime": {"key": "capture_datetime", "scope": "encounter", "type": "datetime"},
    "project_unique_id_patient": {"key": "project_unique_id_patient", "scope": "patient", "type": "text"},
    "laterality": {"key": "laterality", "scope": "image", "type": "select"},
}


class CsvInferenceError(ValueError):
    """Raised when a CSV cannot safely produce a draft configuration."""


@dataclass(frozen=True)
class CsvInferenceResult:
    """Draft EncounterSetType schema and import-mapper contract."""

    payload: dict[str, Any]


def infer_csv_configuration(stream: BinaryIO, filename: str | None) -> CsvInferenceResult:
    """Profile a bounded UTF-8 CSV without retaining or returning its rows."""
    raw = stream.read(MAX_CSV_BYTES + 1)
    if len(raw) > MAX_CSV_BYTES:
        raise CsvInferenceError(f"CSV exceeds the {MAX_CSV_BYTES // (1024 * 1024)} MB analysis limit.")
    if not raw:
        raise CsvInferenceError("CSV file is empty.")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CsvInferenceError("CSV must be UTF-8 encoded.") from exc

    reader = csv.DictReader(io.StringIO(text, newline=""))
    headers = _validate_headers(reader.fieldnames)
    values: dict[str, list[str]] = {header: [] for header in headers}
    row_count = 0
    malformed_rows = 0
    try:
        for row in reader:
            row_count += 1
            if row_count > MAX_ROWS:
                raise CsvInferenceError(f"CSV exceeds the {MAX_ROWS} row analysis limit.")
            if None in row:
                malformed_rows += 1
            for header in headers:
                value = str(row.get(header) or "").strip()
                if value:
                    values[header].append(value)
    except csv.Error as exc:
        raise CsvInferenceError(f"CSV could not be parsed: {exc}.") from exc
    if row_count == 0:
        raise CsvInferenceError("CSV contains headers but no data rows.")
    if malformed_rows:
        raise CsvInferenceError(f"CSV contains {malformed_rows} row(s) with more values than headers.")

    fields, mappings, reserved, excluded, warnings = _build_draft(headers, values)
    source_name = PurePath(filename or "dataset.csv").name
    header_fingerprint = hashlib.sha256("\x1f".join(headers).encode("utf-8")).hexdigest()
    return CsvInferenceResult(
        payload={
            "source": {
                "filename": source_name,
                "row_count": row_count,
                "column_count": len(headers),
                "header_fingerprint": header_fingerprint,
            },
            "metadata_schema_json": {"fields": fields},
            "asset_rules_json": {
                "allow_clinical_images": True,
                "min_clinical_images": 1,
                "max_clinical_images": 2,
                "allow_document_uploads": False,
                "allow_pdf_uploads": False,
                "allow_document_image_uploads": False,
                "max_documents": None,
                "max_pdfs": None,
                "max_document_images": None,
                "allow_report_uploads": False,
                "allow_report_pdfs": False,
                "allow_report_images": False,
                "max_reports": None,
            },
            "mapper_draft": {
                "version": 1,
                "status": "draft",
                "header_fingerprint": header_fingerprint,
                "column_mappings": mappings,
                "reserved_columns": reserved,
                "excluded_columns": excluded,
            },
            "warnings": warnings,
            "privacy": {
                "rows_persisted": False,
                "row_samples_returned": False,
                "distinct_select_options_returned": True,
                "source_file_persisted": False,
            },
        }
    )


def _validate_headers(fieldnames: list[str] | None) -> list[str]:
    if not fieldnames:
        raise CsvInferenceError("CSV header row is missing.")
    if len(fieldnames) > MAX_COLUMNS:
        raise CsvInferenceError(f"CSV exceeds the {MAX_COLUMNS} column analysis limit.")
    headers = [str(header or "").strip() for header in fieldnames]
    if any(not header for header in headers):
        raise CsvInferenceError("CSV contains a blank column header.")
    duplicates = sorted(header for header, count in Counter(headers).items() if count > 1)
    if duplicates:
        raise CsvInferenceError(f"CSV contains duplicate header(s): {', '.join(duplicates)}.")
    return headers


def _build_draft(
    headers: list[str], values: dict[str, list[str]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    fields: list[dict[str, Any]] = []
    mappings: list[dict[str, Any]] = []
    reserved: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    warnings: list[str] = []
    consumed: set[str] = set()

    for header in headers:
        if header in _RESERVED_KEYS:
            role = _RESERVED_KEYS[header]
            canonical = "project_unique_id_patient" if role == "encounter_identity" else "capture_datetime"
            reserved.append({"source_column": header, "role": role, "canonical_key": canonical})
            consumed.add(header)

    eye_groups: dict[str, dict[str, str]] = {}
    for header in headers:
        parsed = _eye_header(header)
        if parsed:
            base, suffix, _laterality = parsed
            eye_groups.setdefault(base, {})[suffix] = header

    for base, members in eye_groups.items():
        if base in consumed:
            continue
        conventions = [pair for pair in _PAIR_FAMILIES if pair[0] in members or pair[1] in members]
        if len(conventions) > 1:
            raise CsvInferenceError(
                f"Eye field '{base}' mixes suffix conventions; use only one of _od/_os, _rt/_lt, or _re/_le."
            )
        pair = conventions[0]
        source_columns = [members[suffix] for suffix in pair if suffix in members]
        if _looks_like_image_reference(source_columns, values):
            for suffix in pair:
                if suffix in members:
                    reserved.append(
                        {
                            "source_column": members[suffix],
                            "role": "clinical_image_filename",
                            "laterality": _EYE_SUFFIXES[suffix],
                        }
                    )
                    consumed.add(members[suffix])
            if len(source_columns) == 1:
                warnings.append(f"Image reference '{base}' has only one eye column.")
            continue

        combined = [value for source in source_columns for value in values[source]]
        field = _field(base, _label(base), "image", combined, len(fields) + 1)
        fields.append(field)
        for suffix in pair:
            if suffix in members:
                mappings.append(
                    {
                        "source_column": members[suffix],
                        "canonical_key": base,
                        "scope": "image",
                        "laterality": _EYE_SUFFIXES[suffix],
                    }
                )
                consumed.add(members[suffix])
        missing = [suffix for suffix in pair if suffix not in members]
        if missing:
            warnings.append(f"Image metadata field '{base}' is missing its _{missing[0]} column.")

    for header in headers:
        if header in consumed:
            continue
        column_values = values[header]
        if not column_values:
            excluded.append({"source_column": header, "reason": "empty_column"})
            continue
        if not _KEY_RE.match(header):
            excluded.append({"source_column": header, "reason": "invalid_metadata_key"})
            warnings.append(f"Column '{header}' needs an explicit valid canonical key.")
            continue
        if header in _PATIENT_CANONICAL:
            scope = "patient"
            canonical = _PATIENT_CANONICAL[header]
        else:
            scope = "encounter"
            canonical = _ENCOUNTER_CANONICAL.get(header, header)
        field = _field(canonical, _label(canonical), scope, column_values, len(fields) + 1)
        field["is_pii"] = canonical in _PII_KEYS
        fields.append(field)
        mappings.append({"source_column": header, "canonical_key": canonical, "scope": scope})

    laterality = {
        "key": "laterality",
        "label": "Laterality",
        "scope": "image",
        "type": "select",
        "selection_mode": "single",
        "options": [{"value": "OD", "label": "OD"}, {"value": "OS", "label": "OS"}],
        "display_order": 0,
        "required_at_upload": True,
        "editable_during_verification": True,
        "visible_to_grader": True,
        "is_pii": False,
        "master_hint": _CANONICAL_MASTER_HINTS["laterality"],
    }
    fields.insert(0, laterality)
    for order, field in enumerate(fields, start=1):
        field["display_order"] = order
    return fields, mappings, reserved, excluded, warnings


def _eye_header(header: str) -> tuple[str, str, str] | None:
    match = re.match(r"^(.+)_([A-Za-z]{2})$", header)
    if not match:
        return None
    base, suffix = match.group(1), match.group(2).lower()
    if suffix not in _EYE_SUFFIXES:
        return None
    return base, suffix, _EYE_SUFFIXES[suffix]


def _looks_like_image_reference(columns: list[str], values: dict[str, list[str]]) -> bool:
    samples = [value for column in columns for value in values[column][:500]]
    if not samples:
        return any(token in column.lower() for column in columns for token in ("photo", "filename", "file_path"))
    image_like = sum(PurePath(value).suffix.lower() in _IMAGE_EXTENSIONS for value in samples)
    return image_like / len(samples) >= 0.8


def _field(key: str, label: str, scope: str, values: list[str], order: int) -> dict[str, Any]:
    field_type, options = _infer_type(values)
    field_type = _TYPE_OVERRIDES.get(key, field_type)
    if field_type != "select":
        options = []
    field: dict[str, Any] = {
        "key": key,
        "label": label,
        "scope": scope,
        "type": field_type,
        "display_order": order,
        "required_at_upload": False,
        "editable_during_verification": True,
        "visible_to_grader": scope == "image",
        "is_pii": False,
    }
    if field_type == "select":
        field["selection_mode"] = "single"
        field["options"] = [{"value": option, "label": option} for option in options]
    hint = _CANONICAL_MASTER_HINTS.get(key)
    if hint:
        field["master_hint"] = hint
    return field


def _infer_type(values: list[str]) -> tuple[str, list[str]]:
    unique = sorted(set(values))
    if values and all(_is_integer(value) for value in values):
        return "integer", []
    if values and all(_is_decimal(value) for value in values):
        return "decimal", []
    if values and all(_is_datetime(value) for value in values):
        return "datetime", []
    if values and all(_is_date(value) for value in values):
        return "date", []
    if unique and len(unique) <= MAX_SELECT_OPTIONS and all(len(value) <= MAX_OPTION_LENGTH for value in unique):
        return "select", unique
    if any(len(value) > 255 or "\n" in value for value in values):
        return "textarea", []
    return "text", []


def _is_integer(value: str) -> bool:
    try:
        int(value)
        return not any(char in value for char in (".", "e", "E"))
    except ValueError:
        return False


def _is_decimal(value: str) -> bool:
    try:
        Decimal(value)
        return True
    except InvalidOperation:
        return False


def _is_datetime(value: str) -> bool:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return "T" in value or " " in value or parsed.tzinfo is not None
    except ValueError:
        return False


def _is_date(value: str) -> bool:
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def _label(key: str) -> str:
    replacements = {"co": "CO", "va": "VA", "id": "ID"}
    return " ".join(replacements.get(part.lower(), part.capitalize()) for part in key.split("_"))
