"""Shared validation for mobile EncounterSet capture payloads.

This module has no Flask or database dependency so upload adapters can validate
the same EncounterSetType contract before persisting any part of a capture.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from typing import Any, Mapping, Sequence

from encounter_set_types.service import normalize_asset_rules, normalize_metadata_schema


SUPPORTED_CAPTURE_FIELD_TYPES = frozenset(
    {"text", "textarea", "integer", "decimal", "date", "datetime", "boolean", "select", "phone", "email"}
)
ASSET_KINDS = frozenset(
    {"document", "pdf", "document_image", "report", "report_pdf", "report_image"}
)


@dataclass(frozen=True)
class CaptureImage:
    file_key: str
    spatial_position: int
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CaptureDocument:
    file_key: str
    kind: str = "document"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CaptureMetadata:
    """Metadata values, grouped by their EncounterSetType scope."""

    patient: Mapping[str, Any] = field(default_factory=dict)
    encounter: Mapping[str, Any] = field(default_factory=dict)
    upload: Mapping[str, Any] = field(default_factory=dict)
    images: Sequence[Mapping[str, Any]] = field(default_factory=tuple)
    documents: Sequence[Mapping[str, Any]] = field(default_factory=tuple)


@dataclass(frozen=True)
class CaptureValidationInput:
    metadata_schema_json: Any
    asset_rules_json: Any
    metadata: CaptureMetadata
    images: Sequence[CaptureImage]
    multipart_file_keys: Sequence[str]
    documents: Sequence[CaptureDocument] = field(default_factory=tuple)
    expected_configuration_fingerprint: str | None = None


@dataclass(frozen=True)
class CaptureValidationIssue:
    code: str
    message: str
    scope: str | None = None
    field_key: str | None = None


@dataclass(frozen=True)
class CaptureValidationResult:
    valid: bool
    errors: tuple[CaptureValidationIssue, ...] = ()
    configuration_fingerprint: str | None = None


def capture_configuration_fingerprint(metadata_schema_json: Any, asset_rules_json: Any) -> str:
    """Return the stable v1 fingerprint for a normalized capture contract."""
    schema = normalize_metadata_schema(metadata_schema_json)
    rules_result = normalize_asset_rules(asset_rules_json)
    if not rules_result.success:
        raise ValueError(rules_result.message)
    canonical = json.dumps(
        {
            "manifest_version": 1,
            "metadata_schema_json": schema,
            "asset_rules_json": rules_result.payload["asset_rules_json"],
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_capture(request: CaptureValidationInput) -> CaptureValidationResult:
    """Validate capture metadata, asset rules, spatial positions, and file keys."""
    errors: list[CaptureValidationIssue] = []
    try:
        schema = normalize_metadata_schema(request.metadata_schema_json)
    except (TypeError, ValueError) as exc:
        return CaptureValidationResult(False, (CaptureValidationIssue("invalid_schema", str(exc)),))

    rules_result = normalize_asset_rules(request.asset_rules_json)
    if not rules_result.success:
        return CaptureValidationResult(
            False,
            (CaptureValidationIssue("invalid_asset_rules", rules_result.message),),
        )
    rules = rules_result.payload["asset_rules_json"]
    fingerprint = capture_configuration_fingerprint(schema, rules)
    if (
        request.expected_configuration_fingerprint is not None
        and request.expected_configuration_fingerprint != fingerprint
    ):
        errors.append(CaptureValidationIssue(
            "configuration_fingerprint_mismatch",
            "Capture configuration no longer matches the supplied manifest.",
        ))

    fields_by_scope: dict[str, list[dict[str, Any]]] = {
        "patient": [], "encounter": [], "upload": [], "image": [], "document": []
    }
    for spec in schema["fields"]:
        if spec["type"] not in SUPPORTED_CAPTURE_FIELD_TYPES:
            errors.append(CaptureValidationIssue(
                "unsupported_field_type",
                f"Field '{spec['key']}' has unsupported capture type '{spec['type']}'.",
                spec["scope"], spec["key"],
            ))
        else:
            fields_by_scope[spec["scope"]].append(spec)

    _validate_scope_values("patient", request.metadata.patient, fields_by_scope["patient"], errors)
    _validate_scope_values("encounter", request.metadata.encounter, fields_by_scope["encounter"], errors)
    _validate_scope_values("upload", request.metadata.upload, fields_by_scope["upload"], errors)

    image_values = list(request.metadata.images)
    if fields_by_scope["image"] and len(image_values) != len(request.images):
        errors.append(CaptureValidationIssue(
            "image_metadata_count_mismatch",
            "Image metadata must have one entry for each uploaded image.",
            "image",
        ))
    for index, values in enumerate(image_values):
        _validate_scope_values("image", values, fields_by_scope["image"], errors, entry=index + 1)

    document_values = list(request.metadata.documents)
    if fields_by_scope["document"] and len(document_values) != len(request.documents):
        errors.append(CaptureValidationIssue(
            "document_metadata_count_mismatch",
            "Document metadata must have one entry for each uploaded document.",
            "document",
        ))
    for index, values in enumerate(document_values):
        _validate_scope_values("document", values, fields_by_scope["document"], errors, entry=index + 1)

    _validate_assets(request, rules, errors)
    _validate_file_keys(request, errors)
    return CaptureValidationResult(not errors, tuple(errors), fingerprint)


def _validate_scope_values(
    scope: str,
    values: Mapping[str, Any],
    specs: Sequence[dict[str, Any]],
    errors: list[CaptureValidationIssue],
    *,
    entry: int | None = None,
) -> None:
    if not isinstance(values, Mapping):
        errors.append(CaptureValidationIssue("invalid_metadata", f"{scope} metadata must be an object.", scope))
        return
    prefix = f"{scope} entry {entry}: " if entry is not None else ""
    by_key = {spec["key"]: spec for spec in specs}
    for key in values:
        if key not in by_key:
            errors.append(CaptureValidationIssue(
                "unknown_metadata_field", f"{prefix}Unknown {scope} metadata field '{key}'.", scope, str(key)
            ))
    for key, spec in by_key.items():
        value = values.get(key)
        empty = value is None or (isinstance(value, str) and not value.strip()) or value == []
        if empty:
            if spec["required_at_upload"]:
                errors.append(CaptureValidationIssue(
                    "required_metadata_missing", f"{prefix}{spec['label']} is required.", scope, key
                ))
            continue
        issue = _validate_value(spec, value)
        if issue is not None:
            code, message = issue
            errors.append(CaptureValidationIssue(code, f"{prefix}{message}", scope, key))


def _validate_value(spec: dict[str, Any], value: Any) -> tuple[str, str] | None:
    kind, label = spec["type"], spec["label"]
    invalid = ("invalid_metadata_value", f"{label} has an invalid {kind} value.")
    if kind in {"text", "textarea", "phone", "email"}:
        if not isinstance(value, str):
            return invalid
        if kind == "email" and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value.strip()):
            return invalid
        if kind == "phone" and not re.fullmatch(r"\+?[0-9().\-\s]{3,32}", value.strip()):
            return invalid
    elif kind == "integer":
        if isinstance(value, bool) or not re.fullmatch(r"[+-]?\d+", str(value).strip()):
            return invalid
    elif kind == "decimal":
        try:
            number = Decimal(str(value).strip())
            if not number.is_finite():
                return invalid
        except (InvalidOperation, ValueError):
            return invalid
    elif kind == "date":
        if not isinstance(value, date) or isinstance(value, datetime):
            try:
                date.fromisoformat(str(value).strip())
            except ValueError:
                return invalid
    elif kind == "datetime":
        try:
            if not isinstance(value, datetime):
                datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        except ValueError:
            return invalid
    elif kind == "boolean":
        if not isinstance(value, bool) and value not in (0, 1, "0", "1", "true", "false", "True", "False"):
            return invalid
    elif kind == "select":
        option_values = {option["value"] for option in spec.get("options") or []}
        selected = value
        if spec["selection_mode"] == "multiple":
            if not isinstance(value, (list, tuple)) or any(not isinstance(item, (str, int, float)) for item in value):
                return invalid
            if len(set(value)) != len(value) or any(item not in option_values for item in value):
                return ("invalid_select_option", f"{label} contains an unconfigured or duplicate option.")
            return _validate_regex(spec, ",".join(str(item) for item in value), label)
        if isinstance(selected, (list, dict)) or selected not in option_values:
            return ("invalid_select_option", f"{label} must use a configured option.")
        return _validate_regex(spec, str(selected), label)
    return _validate_regex(spec, str(value), label)


def _validate_regex(spec: dict[str, Any], value: str, label: str) -> tuple[str, str] | None:
    pattern = spec.get("validation_regex")
    if pattern and re.fullmatch(pattern, value) is None:
        return (
            "validation_regex_failed",
            spec.get("validation_error_message") or f"{label} has an invalid format.",
        )
    return None


def _validate_assets(request: CaptureValidationInput, rules: Mapping[str, Any], errors: list[CaptureValidationIssue]) -> None:
    image_count = len(request.images)
    _check_allowed_count(image_count, "allow_clinical_images", "max_clinical_images", "clinical images", rules, errors)
    min_images = rules.get("min_clinical_images")
    if min_images is not None and image_count < min_images:
        errors.append(CaptureValidationIssue("min_asset_count", f"At least {min_images} clinical images are required."))

    kind_rule = {
        "document": ("allow_document_uploads",),
        "pdf": ("allow_pdf_uploads",),
        "document_image": ("allow_document_image_uploads",),
        "report": ("allow_report_uploads",),
        "report_pdf": ("allow_report_pdfs",),
        "report_image": ("allow_report_images",),
    }
    counts: dict[str, int] = {kind: 0 for kind in ASSET_KINDS}
    for document in request.documents:
        if document.kind not in kind_rule:
            errors.append(CaptureValidationIssue("invalid_asset_kind", f"Unsupported uploaded asset kind '{document.kind}'."))
            continue
        counts[document.kind] += 1
    for kind, count in counts.items():
        if not count:
            continue
        umbrella_key = "allow_report_uploads" if kind.startswith("report") else "allow_document_uploads"
        if not rules.get(umbrella_key, False):
            errors.append(CaptureValidationIssue(
                "asset_not_allowed",
                f"{kind.replace('_', ' ').capitalize()} uploads require {umbrella_key} to be enabled.",
            ))
        subtype_key = kind_rule[kind][0]
        if subtype_key != umbrella_key and not rules.get(subtype_key, False):
            errors.append(CaptureValidationIssue(
                "asset_not_allowed",
                f"{kind.replace('_', ' ').capitalize()} uploads require {subtype_key} to be enabled.",
            ))
    document_count = counts["document"] + counts["pdf"] + counts["document_image"]
    report_count = counts["report"] + counts["report_pdf"] + counts["report_image"]
    _check_maximum(document_count, "max_documents", "documents", rules, errors)
    _check_maximum(counts["pdf"], "max_pdfs", "PDFs", rules, errors)
    _check_maximum(counts["document_image"], "max_document_images", "document images", rules, errors)
    _check_maximum(report_count, "max_reports", "reports", rules, errors)


def _check_allowed_count(
    count: int, allow_key: str, max_key: str, label: str, rules: Mapping[str, Any], errors: list[CaptureValidationIssue]
) -> None:
    if count and not rules.get(allow_key, False):
        errors.append(CaptureValidationIssue("asset_not_allowed", f"{label.capitalize()} are not allowed for this EncounterSetType."))
    _check_maximum(count, max_key, label, rules, errors)


def _check_maximum(count: int, max_key: str, label: str, rules: Mapping[str, Any], errors: list[CaptureValidationIssue]) -> None:
    maximum = rules.get(max_key)
    if maximum is not None and count > maximum:
        errors.append(CaptureValidationIssue("max_asset_count", f"At most {maximum} {label} are allowed."))


def _validate_file_keys(request: CaptureValidationInput, errors: list[CaptureValidationIssue]) -> None:
    supplied = [str(key).strip() for key in request.multipart_file_keys]
    if any(not key for key in supplied):
        errors.append(CaptureValidationIssue("invalid_file_key", "Multipart file keys must be non-empty strings."))
    if len(supplied) != len(set(supplied)):
        errors.append(CaptureValidationIssue("duplicate_file_key", "Multipart file keys must be unique."))
    expected: list[str] = []
    positions: set[int] = set()
    for image in request.images:
        key = image.file_key.strip() if isinstance(image.file_key, str) else ""
        expected.append(key)
        if not isinstance(image.spatial_position, int) or isinstance(image.spatial_position, bool) or not 1 <= image.spatial_position <= 9:
            errors.append(CaptureValidationIssue("invalid_spatial_position", "Image spatial_position must be an integer from 1 to 9.", "image"))
        elif image.spatial_position in positions:
            errors.append(CaptureValidationIssue("duplicate_spatial_position", "Image spatial_position values must be unique.", "image"))
        else:
            positions.add(image.spatial_position)
    expected.extend(asset.file_key.strip() if isinstance(asset.file_key, str) else "" for asset in request.documents)
    if any(not key for key in expected):
        errors.append(CaptureValidationIssue("invalid_file_key", "Each uploaded asset must have a non-empty file_key."))
    if len(expected) != len(set(expected)):
        errors.append(CaptureValidationIssue("duplicate_file_key", "Uploaded asset file_key values must be unique."))
    supplied_set, expected_set = set(supplied), set(expected)
    for key in sorted(expected_set - supplied_set):
        errors.append(CaptureValidationIssue("file_part_missing", f"Multipart file part for file_key '{key}' is missing."))
    for key in sorted(supplied_set - expected_set):
        errors.append(CaptureValidationIssue("unreferenced_file_part", f"Multipart file part '{key}' is not referenced by the capture."))
