from encounter_set_types.capture_validation import (
    CaptureDocument,
    CaptureImage,
    CaptureMetadata,
    CaptureValidationInput,
    capture_configuration_fingerprint,
    validate_capture,
)
from encounter_set_types.models import default_asset_rules


def _schema(fields=None):
    return {"fields": fields or []}


def _rules(**overrides):
    result = default_asset_rules()
    result.update(overrides)
    return result


def _capture(**overrides):
    values = {
        "metadata_schema_json": _schema(),
        "asset_rules_json": _rules(),
        "metadata": CaptureMetadata(),
        "images": (CaptureImage("image-1", 1),),
        "multipart_file_keys": ("image-1",),
    }
    values.update(overrides)
    return CaptureValidationInput(**values)


def test_capture_accepts_all_supported_metadata_types_and_scopes():
    fields = [
        {"key": "name", "label": "Name", "scope": "patient", "type": "text", "required_at_upload": True},
        {"key": "notes", "label": "Notes", "scope": "encounter", "type": "textarea"},
        {"key": "age", "label": "Age", "scope": "patient", "type": "integer"},
        {"key": "weight", "label": "Weight", "scope": "encounter", "type": "decimal"},
        {"key": "visit_day", "label": "Visit day", "scope": "encounter", "type": "date"},
        {"key": "observed_at", "label": "Observed at", "scope": "upload", "type": "datetime"},
        {"key": "consent", "label": "Consent", "scope": "document", "type": "boolean"},
        {"key": "eye", "label": "Eye", "scope": "image", "type": "select", "options": ["OD", "OS"]},
        {"key": "tags", "label": "Tags", "scope": "upload", "type": "select", "selection_mode": "multiple", "options": ["a", "b"]},
        {"key": "phone", "label": "Phone", "scope": "patient", "type": "phone"},
        {"key": "email", "label": "Email", "scope": "patient", "type": "email"},
    ]
    capture = _capture(
        metadata_schema_json=_schema(fields),
        metadata=CaptureMetadata(
            patient={"name": "P-100", "age": "42", "phone": "+1 (555) 123-4567", "email": "a@example.org"},
            encounter={"notes": "Routine", "weight": "60.5", "visit_day": "2026-09-25"},
            upload={"observed_at": "2026-09-25T10:15:00Z", "tags": ["a", "b"]},
            images=({"eye": "OD"},),
        ),
    )

    result = validate_capture(capture)

    assert result.valid
    assert result.configuration_fingerprint == capture_configuration_fingerprint(capture.metadata_schema_json, capture.asset_rules_json)


def test_capture_rejects_unknown_required_invalid_and_regex_values():
    schema = _schema([
        {"key": "patient_code", "label": "Patient code", "scope": "patient", "type": "text", "required_at_upload": True},
        {"key": "email", "label": "Email", "scope": "patient", "type": "email", "validation_regex": r".+@clinic\.org", "validation_error_message": "Use your clinic email."},
    ])
    result = validate_capture(_capture(metadata_schema_json=schema, metadata=CaptureMetadata(patient={"unexpected": "x", "email": "bad@example.com"})))

    assert not result.valid
    assert {issue.code for issue in result.errors} == {
        "unknown_metadata_field", "required_metadata_missing", "validation_regex_failed"
    }
    assert any(issue.message == "Use your clinic email." for issue in result.errors)


def test_capture_checks_single_and_multiple_select_options():
    schema = _schema([
        {"key": "eye", "label": "Eye", "scope": "image", "type": "select", "options": ["OD", "OS"]},
        {"key": "tags", "label": "Tags", "scope": "upload", "type": "select", "selection_mode": "multiple", "options": ["a", "b"]},
    ])
    result = validate_capture(_capture(
        metadata_schema_json=schema,
        metadata=CaptureMetadata(upload={"tags": ["a", "not-configured"]}, images=({"eye": "OU"},)),
    ))

    assert not result.valid
    assert [issue.code for issue in result.errors] == ["invalid_select_option", "invalid_select_option"]


def test_capture_rejects_json_type_and_required_image_value_per_item():
    schema = _schema([
        {"key": "extra", "label": "Extra", "scope": "upload", "type": "json"},
        {"key": "eye", "label": "Eye", "scope": "image", "type": "text", "required_at_upload": True},
    ])
    capture = _capture(
        metadata_schema_json=schema,
        images=(CaptureImage("image-1", 1), CaptureImage("image-2", 2)),
        multipart_file_keys=("image-1", "image-2"),
        metadata=CaptureMetadata(images=({}, {})),
    )

    result = validate_capture(capture)

    assert {issue.code for issue in result.errors} == {"unsupported_field_type", "required_metadata_missing"}
    assert sum(issue.code == "required_metadata_missing" for issue in result.errors) == 2


def test_capture_enforces_asset_allowances_counts_positions_and_file_keys():
    rules = _rules(
        max_clinical_images=1,
        allow_document_uploads=True,
        max_documents=1,
        allow_pdf_uploads=True,
        max_pdfs=0,
    )
    capture = _capture(
        asset_rules_json=rules,
        images=(CaptureImage("same", 1), CaptureImage("same", 1), CaptureImage("invalid-position", 10)),
        documents=(CaptureDocument("same", "pdf"),),
        multipart_file_keys=("same", "orphan"),
    )

    result = validate_capture(capture)
    codes = {issue.code for issue in result.errors}
    assert {"max_asset_count", "invalid_spatial_position", "duplicate_spatial_position", "duplicate_file_key", "unreferenced_file_part"} <= codes


def test_document_subtypes_require_their_umbrella_allowance():
    capture = _capture(
        asset_rules_json=_rules(allow_pdf_uploads=True),
        images=(),
        multipart_file_keys=("doc",),
        documents=(CaptureDocument("doc", "pdf"),),
    )

    result = validate_capture(capture)

    assert not result.valid
    assert any("allow_document_uploads" in issue.message for issue in result.errors)


def test_capture_detects_manifest_configuration_change():
    schema, rules = _schema(), _rules()
    stale_fingerprint = capture_configuration_fingerprint(schema, rules)
    capture = _capture(
        asset_rules_json=_rules(max_clinical_images=2),
        expected_configuration_fingerprint=stale_fingerprint,
    )

    result = validate_capture(capture)

    assert not result.valid
    assert result.errors[0].code == "configuration_fingerprint_mismatch"


def test_configuration_fingerprint_is_stable_for_normalized_input():
    assert capture_configuration_fingerprint(_schema(), _rules()) == capture_configuration_fingerprint(
        {"fields": None}, None
    )
