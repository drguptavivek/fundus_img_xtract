"""Service layer for EncounterSetType administration."""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any

import db_transaction_manager
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from auth.utils import utcnow
from encounter_set_types.models import EncounterSetType, default_asset_rules
from upload_metadata.models import UploadMetadataFieldDefinition
from upload_profiles.admin_service import MutationResult
from upload_profiles.models import UploadProfileEncounterSetType
from upload_profiles.service import manager_lab_unit_ids


SUPPORTED_FIELD_TYPES = {
    "text",
    "textarea",
    "integer",
    "decimal",
    "date",
    "datetime",
    "boolean",
    "json",
    "select",
    "phone",
    "email",
}
SUPPORTED_SCOPES = {"patient", "encounter", "image", "document", "upload"}
SUPPORTED_SELECTION_MODES = {"single", "multiple"}
_KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_CODE_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


@dataclass
class EncounterSetTypeInput:
    name: str
    code: str
    metadata_schema_json: dict[str, Any]
    asset_rules_json: dict[str, Any] | None = None
    description: str | None = None
    active: bool = True


def list_encounter_set_types(
    manager_user_id: int,
    *,
    include_inactive: bool = False,
) -> list[dict[str, Any]]:
    """List reusable encounter-set types for managers with upload metadata scope."""
    with db_transaction_manager.transaction_scope() as db:
        if not _has_manager_scope(manager_user_id):
            return []
        query = (
            select(EncounterSetType)
            .order_by(EncounterSetType.active.desc(), EncounterSetType.name)
        )
        if not include_inactive:
            query = query.where(EncounterSetType.active.is_(True))
        rows = db.execute(query).scalars().all()
        return [serialize_encounter_set_type(row) for row in rows]


def get_encounter_set_type(manager_user_id: int, type_id: int) -> MutationResult:
    with db_transaction_manager.transaction_scope() as db:
        row = _get_scoped_type(db, manager_user_id, type_id)
        if row is None:
            return MutationResult(False, "Encounter-set type not found.", 404)
        return MutationResult(
            True,
            "Encounter-set type found.",
            payload={"encounter_set_type": serialize_encounter_set_type(row)},
        )


def export_encounter_set_type_schema(manager_user_id: int, type_id: int) -> MutationResult:
    """Return a portable EncounterSetType schema export payload."""
    with db_transaction_manager.transaction_scope() as db:
        row = _get_scoped_type(db, manager_user_id, type_id)
        if row is None:
            return MutationResult(False, "Encounter-set type not found.", 404)
        return MutationResult(
            True,
            "Encounter-set type schema exported.",
            payload={
                "schema": {
                    "schema_type": "encounter_set_type",
                    "schema_version": 1,
                    "exported_at": utcnow().isoformat(),
                    "encounter_set_type": {
                        "id": row.id,
                        "name": row.name,
                        "code": row.code,
                        "description": row.description,
                        "active": row.active,
                    },
                    "asset_rules_json": row.asset_rules_json or default_asset_rules(),
                    "metadata_schema_json": row.metadata_schema_json or {"fields": []},
                },
                "filename": f"{row.code or row.id}_encounter_set_type_schema.json",
            },
        )


def create_encounter_set_type(manager_user_id: int, dto: EncounterSetTypeInput) -> MutationResult:
    error = validate_encounter_set_type_input(dto)
    if error:
        return MutationResult(False, error, 400)
    with db_transaction_manager.transaction_scope() as db:
        if not _has_manager_scope(manager_user_id):
            return MutationResult(False, "You are not assigned to any lab units for upload metadata management.", 403)
        asset_rules_result = normalize_asset_rules(dto.asset_rules_json)
        if not asset_rules_result.success:
            return asset_rules_result
        schema_result = _schema_with_master_fields(db, manager_user_id, dto.metadata_schema_json)
        if not schema_result.success:
            return schema_result
        row = EncounterSetType(
            name=dto.name.strip(),
            code=dto.code.strip(),
            description=dto.description,
            metadata_schema_json=schema_result.payload["metadata_schema_json"],
            asset_rules_json=asset_rules_result.payload["asset_rules_json"],
            active=dto.active,
            created_by_user_id=manager_user_id,
            updated_by_user_id=manager_user_id,
        )
        db.add(row)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return MutationResult(False, "Encounter-set type code already exists.", 400)
        return MutationResult(
            True,
            "Encounter-set type created.",
            201,
            payload={"encounter_set_type": serialize_encounter_set_type(row)},
        )


def update_encounter_set_type(manager_user_id: int, type_id: int, dto: EncounterSetTypeInput) -> MutationResult:
    error = validate_encounter_set_type_input(dto)
    if error:
        return MutationResult(False, error, 400)
    with db_transaction_manager.transaction_scope() as db:
        row = _get_scoped_type(db, manager_user_id, type_id)
        if row is None:
            return MutationResult(False, "Encounter-set type not found.", 404)
        asset_rules_result = normalize_asset_rules(dto.asset_rules_json)
        if not asset_rules_result.success:
            return asset_rules_result
        row.name = dto.name.strip()
        row.code = dto.code.strip()
        row.description = dto.description
        schema_result = _schema_with_master_fields(db, manager_user_id, dto.metadata_schema_json)
        if not schema_result.success:
            return schema_result
        row.metadata_schema_json = schema_result.payload["metadata_schema_json"]
        row.asset_rules_json = asset_rules_result.payload["asset_rules_json"]
        row.active = dto.active
        row.updated_by_user_id = manager_user_id
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return MutationResult(False, "Encounter-set type code already exists.", 400)
        return MutationResult(
            True,
            "Encounter-set type updated.",
            payload={"encounter_set_type": serialize_encounter_set_type(row)},
        )


def set_encounter_set_type_active(manager_user_id: int, type_id: int, active: bool) -> MutationResult:
    with db_transaction_manager.transaction_scope() as db:
        row = _get_scoped_type(db, manager_user_id, type_id)
        if row is None:
            return MutationResult(False, "Encounter-set type not found.", 404)
        row.active = active
        row.updated_by_user_id = manager_user_id
        return MutationResult(
            True,
            "Encounter-set type activated." if active else "Encounter-set type deactivated.",
            payload={"encounter_set_type": serialize_encounter_set_type(row)},
        )


def delete_encounter_set_type(manager_user_id: int, type_id: int) -> MutationResult:
    """Delete an encounter-set type only when no upload profile references it."""
    with db_transaction_manager.transaction_scope() as db:
        row = _get_scoped_type(db, manager_user_id, type_id)
        if row is None:
            return MutationResult(False, "Encounter-set type not found.", 404)
        linked_profile_count = db.execute(
            select(func.count(UploadProfileEncounterSetType.id)).where(
                UploadProfileEncounterSetType.encounter_set_type_id == type_id
            )
        ).scalar_one()
        if linked_profile_count:
            return MutationResult(
                False,
                "Encounter-set type is linked to one or more upload profiles and cannot be deleted.",
                400,
            )
        db.delete(row)
        return MutationResult(True, "Encounter-set type deleted.")


def validate_encounter_set_type_input(dto: EncounterSetTypeInput) -> str | None:
    if not (dto.name or "").strip():
        return "Encounter-set type name is required."
    if not (dto.code or "").strip():
        return "Encounter-set type code is required."
    if not _CODE_RE.match(dto.code.strip()):
        return "Encounter-set type code may contain only letters, numbers, underscores, hyphens, and dots."
    try:
        normalize_metadata_schema(dto.metadata_schema_json)
    except ValueError as exc:
        return str(exc)
    return None


def normalize_metadata_schema(raw_schema: Any) -> dict[str, Any]:
    """Validate and normalize an EncounterSetType metadata field-list schema."""
    if raw_schema is None or raw_schema == "":
        raw_schema = {"fields": []}
    if isinstance(raw_schema, str):
        try:
            raw_schema = json.loads(raw_schema)
        except json.JSONDecodeError as exc:
            raise ValueError("metadata_schema_json must be valid JSON.") from exc
    if not isinstance(raw_schema, dict):
        raise ValueError("metadata_schema_json must be an object with a fields list.")
    fields = raw_schema.get("fields", [])
    if fields is None:
        fields = []
    if not isinstance(fields, list):
        raise ValueError("metadata_schema_json.fields must be a list.")
    normalized_fields: list[dict[str, Any]] = []
    seen: set[str] = set()
    for idx, field in enumerate(fields, start=1):
        if not isinstance(field, dict):
            raise ValueError(f"metadata_schema_json.fields[{idx}] must be an object.")
        normalized = _normalize_field(field, idx)
        if normalized["key"] in seen:
            raise ValueError(f"metadata_schema_json.fields[{idx}] duplicates key '{normalized['key']}'.")
        seen.add(normalized["key"])
        normalized_fields.append(normalized)
    return {"fields": normalized_fields}


def normalize_asset_rules(raw_rules: Any) -> MutationResult:
    """Validate and normalize EncounterSetType asset permission rules."""
    rules = default_asset_rules()
    if raw_rules in (None, ""):
        return MutationResult(True, "Asset rules normalized.", payload={"asset_rules_json": rules})
    if isinstance(raw_rules, str):
        try:
            raw_rules = json.loads(raw_rules)
        except json.JSONDecodeError:
            return MutationResult(False, "asset_rules_json must be valid JSON.", 400)
    if not isinstance(raw_rules, dict):
        return MutationResult(False, "asset_rules_json must be an object.", 400)

    bool_keys = {
        "allow_clinical_images",
        "allow_document_uploads",
        "allow_pdf_uploads",
        "allow_document_image_uploads",
        "allow_report_uploads",
        "allow_report_pdfs",
        "allow_report_images",
    }
    int_keys = {
        "min_clinical_images",
        "max_clinical_images",
        "max_documents",
        "max_pdfs",
        "max_document_images",
        "max_reports",
    }
    for key, value in raw_rules.items():
        if key not in rules:
            return MutationResult(False, f"asset_rules_json contains unsupported key '{key}'.", 400)
        if key in bool_keys:
            rules[key] = _coerce_bool(value)
        elif key in int_keys:
            try:
                rules[key] = _optional_non_negative_int(value, key)
            except ValueError as exc:
                return MutationResult(False, str(exc), 400)
    min_images = rules.get("min_clinical_images")
    max_images = rules.get("max_clinical_images")
    if min_images is not None and max_images is not None and min_images > max_images:
        return MutationResult(False, "min_clinical_images cannot be greater than max_clinical_images.", 400)
    return MutationResult(True, "Asset rules normalized.", payload={"asset_rules_json": rules})


def _schema_with_master_fields(db, manager_user_id: int, raw_schema: Any) -> MutationResult:
    """Normalize schema and ensure every field points to a master metadata field."""
    try:
        schema = normalize_metadata_schema(raw_schema)
    except ValueError as exc:
        return MutationResult(False, str(exc), 400)
    for idx, field in enumerate(schema["fields"], start=1):
        result = _resolve_master_field(db, manager_user_id, field, idx)
        if not result.success:
            return result
        field["field_definition_id"] = result.payload["field_definition_id"]
    return MutationResult(True, "Encounter-set metadata schema resolved.", payload={"metadata_schema_json": schema})


def _resolve_master_field(db, manager_user_id: int, field: dict[str, Any], idx: int) -> MutationResult:
    field_definition_id = field.get("field_definition_id")
    if field_definition_id:
        master = db.get(UploadMetadataFieldDefinition, field_definition_id)
        if master is None:
            return MutationResult(False, f"metadata_schema_json.fields[{idx}] field_definition_id does not exist.", 400)
        if master.key != field["key"]:
            return MutationResult(
                False,
                f"metadata_schema_json.fields[{idx}] key must match the selected master field key '{master.key}'.",
                400,
            )
        if master.scope != field["scope"]:
            return MutationResult(
                False,
                f"metadata_schema_json.fields[{idx}] scope must match the selected master field scope '{master.scope}'.",
                400,
            )
        _apply_master_definition_snapshot(field, master)
        return MutationResult(True, "Master field resolved.", payload={"field_definition_id": master.id})

    existing = db.execute(
        select(UploadMetadataFieldDefinition).where(UploadMetadataFieldDefinition.key == field["key"]).limit(1)
    ).scalar_one_or_none()
    if existing is not None:
        if existing.scope != field["scope"]:
            return MutationResult(
                False,
                f"metadata_schema_json.fields[{idx}] key already exists as a {existing.scope} master field.",
                400,
            )
        _apply_master_definition_snapshot(field, existing)
        return MutationResult(True, "Master field resolved.", payload={"field_definition_id": existing.id})

    master = UploadMetadataFieldDefinition(
        scope=field["scope"],
        key=field["key"],
        label=field["label"],
        sctid=field.get("sctid"),
        field_type=field["type"],
        selection_mode=field.get("selection_mode"),
        options_json=field.get("options"),
        description=field.get("description"),
        validation_regex=field.get("validation_regex"),
        validation_error_message=field.get("validation_error_message"),
        required_at_upload_default=field["required_at_upload"],
        required_for_verification_default=field["required_for_verification"],
        visible_to_grader_default=field["visible_to_grader"],
        is_pii_default=field["is_pii"],
        active=True,
        created_by_user_id=manager_user_id,
        updated_by_user_id=manager_user_id,
    )
    db.add(master)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return MutationResult(False, f"metadata_schema_json.fields[{idx}] key already exists in metadata field masters.", 400)
    return MutationResult(True, "Master field created.", payload={"field_definition_id": master.id})


def _apply_master_definition_snapshot(field: dict[str, Any], master: UploadMetadataFieldDefinition) -> None:
    """Keep reusable field definition values canonical while preserving per-type usage settings."""
    field["field_definition_id"] = master.id
    field["key"] = master.key
    field["label"] = master.label
    field["sctid"] = master.sctid
    field["scope"] = master.scope
    field["type"] = master.field_type
    field["selection_mode"] = master.selection_mode if master.field_type == "select" else None
    field["options"] = master.options_json if master.field_type == "select" else None
    field["description"] = master.description
    field["validation_regex"] = master.validation_regex
    field["validation_error_message"] = master.validation_error_message


def serialize_encounter_set_type(row: EncounterSetType) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "code": row.code,
        "description": row.description,
        "metadata_schema_json": row.metadata_schema_json or {"fields": []},
        "asset_rules_json": row.asset_rules_json or default_asset_rules(),
        "active": row.active,
        "created_by_user_id": row.created_by_user_id,
        "updated_by_user_id": row.updated_by_user_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _normalize_field(field: dict[str, Any], idx: int) -> dict[str, Any]:
    key = str(field.get("key") or "").strip()
    if not key or not _KEY_RE.match(key):
        raise ValueError(f"metadata_schema_json.fields[{idx}] requires a valid key.")
    label = str(field.get("label") or "").strip()
    if not label:
        raise ValueError(f"metadata_schema_json.fields[{idx}] requires a label.")
    scope = str(field.get("scope") or "").strip()
    if scope not in SUPPORTED_SCOPES:
        raise ValueError(f"metadata_schema_json.fields[{idx}] scope must be patient, encounter, image, document, or upload.")
    field_type = str(field.get("type") or "").strip()
    if field_type not in SUPPORTED_FIELD_TYPES:
        raise ValueError(f"metadata_schema_json.fields[{idx}] has unsupported type '{field_type}'.")
    selection_mode = field.get("selection_mode")
    if field_type == "select":
        selection_mode = str(selection_mode or "single").strip()
        if selection_mode not in SUPPORTED_SELECTION_MODES:
            raise ValueError(f"metadata_schema_json.fields[{idx}] selection_mode must be single or multiple.")
    elif selection_mode not in (None, ""):
        raise ValueError(f"metadata_schema_json.fields[{idx}] selection_mode is only valid for select fields.")
    else:
        selection_mode = None

    options = field.get("options")
    if options is not None:
        if field_type != "select":
            raise ValueError(f"metadata_schema_json.fields[{idx}] options are only valid for select fields.")
        options = _normalize_options(options, idx)
    validation_regex = (str(field.get("validation_regex")).strip() if field.get("validation_regex") is not None else None) or None
    validation_error_message = (
        str(field.get("validation_error_message")).strip()
        if field.get("validation_error_message") is not None
        else None
    ) or None
    if validation_regex:
        try:
            re.compile(validation_regex)
        except re.error as exc:
            raise ValueError(f"metadata_schema_json.fields[{idx}] validation_regex is invalid: {exc}.") from exc

    return {
        "field_definition_id": _optional_positive_int(field.get("field_definition_id"), idx),
        "key": key,
        "label": label,
        "sctid": (str(field.get("sctid")).strip() if field.get("sctid") is not None else None) or None,
        "scope": scope,
        "type": field_type,
        "display_order": _non_negative_int(field.get("display_order"), idx),
        "selection_mode": selection_mode,
        "options": options,
        "description": (str(field.get("description")).strip() if field.get("description") is not None else None) or None,
        "validation_regex": validation_regex,
        "validation_error_message": validation_error_message,
        "required_at_upload": _bool_field(field, "required_at_upload", idx),
        "required_for_verification": _bool_field(field, "required_for_verification", idx),
        "visible_to_grader": _bool_field(field, "visible_to_grader", idx),
        "is_pii": _bool_field(field, "is_pii", idx),
    }


def _normalize_options(options: Any, idx: int) -> list[dict[str, str]]:
    if not isinstance(options, list):
        raise ValueError(f"metadata_schema_json.fields[{idx}] options must be a list.")
    normalized: list[dict[str, str]] = []
    seen_values: set[str] = set()
    for option_idx, option in enumerate(options, start=1):
        if isinstance(option, str):
            value = option.strip()
            label = value
        elif isinstance(option, dict):
            value = str(option.get("value") or "").strip()
            label = str(option.get("label") or value).strip()
        else:
            raise ValueError(f"metadata_schema_json.fields[{idx}].options[{option_idx}] must be a string or object.")
        if not value:
            raise ValueError(f"metadata_schema_json.fields[{idx}].options[{option_idx}] requires a value.")
        if value in seen_values:
            raise ValueError(f"metadata_schema_json.fields[{idx}] has duplicate option value '{value}'.")
        seen_values.add(value)
        normalized.append({"value": value, "label": label or value})
    return normalized


def _bool_field(field: dict[str, Any], key: str, idx: int) -> bool:
    value = field.get(key, False)
    if not isinstance(value, bool):
        raise ValueError(f"metadata_schema_json.fields[{idx}] {key} must be boolean.")
    return value


def _optional_positive_int(value: Any, idx: int) -> int | None:
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"metadata_schema_json.fields[{idx}] field_definition_id must be an integer.") from exc
    if parsed <= 0:
        raise ValueError(f"metadata_schema_json.fields[{idx}] field_definition_id must be positive.")
    return parsed


def _non_negative_int(value: Any, idx: int) -> int:
    if value in (None, ""):
        return idx
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"metadata_schema_json.fields[{idx}] display_order must be an integer.") from exc
    if parsed < 0:
        raise ValueError(f"metadata_schema_json.fields[{idx}] display_order cannot be negative.")
    return parsed


def _optional_non_negative_int(value: Any, key: str) -> int | None:
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be a non-negative integer.") from exc
    if parsed < 0:
        raise ValueError(f"{key} must be a non-negative integer.")
    return parsed


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _has_manager_scope(manager_user_id: int) -> bool:
    return bool(manager_lab_unit_ids(manager_user_id))


def _get_scoped_type(db, manager_user_id: int, type_id: int) -> EncounterSetType | None:
    if not _has_manager_scope(manager_user_id):
        return None
    return (
        db.execute(
            select(EncounterSetType)
            .where(EncounterSetType.id == type_id)
        )
        .scalars()
        .one_or_none()
    )
