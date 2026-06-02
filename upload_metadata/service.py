"""Service layer for reusable upload metadata field definitions."""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

import db_transaction_manager
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from upload_metadata.models import UploadMetadataFieldDefinition
from upload_profiles.admin_service import MutationResult
from upload_profiles.service import manager_lab_unit_ids


SUPPORTED_FIELD_SCOPES = {"patient", "encounter", "image", "document", "upload"}
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
SUPPORTED_SELECTION_MODES = {"single", "multiple"}
_KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class FieldDefinitionInput:
    scope: str
    key: str
    label: str
    field_type: str
    sctid: str | None = None
    selection_mode: str | None = None
    options_json: list[dict[str, str]] | list[str] | None = None
    description: str | None = None
    validation_regex: str | None = None
    validation_error_message: str | None = None
    required_at_upload_default: bool = False
    editable_during_verification_default: bool = False
    visible_to_grader_default: bool = False
    is_pii_default: bool = False
    active: bool = True


def list_field_definitions(manager_user_id: int, *, include_inactive: bool = False) -> list[dict[str, Any]]:
    if not _has_manager_scope(manager_user_id):
        return []
    with db_transaction_manager.transaction_scope() as db:
        query = select(UploadMetadataFieldDefinition).order_by(
            UploadMetadataFieldDefinition.scope,
            UploadMetadataFieldDefinition.active.desc(),
            UploadMetadataFieldDefinition.label,
        )
        if not include_inactive:
            query = query.where(UploadMetadataFieldDefinition.active.is_(True))
        return [serialize_field_definition(row) for row in db.execute(query).scalars().all()]


def create_field_definition(manager_user_id: int, dto: FieldDefinitionInput) -> MutationResult:
    error = validate_field_definition_input(dto)
    if error:
        return MutationResult(False, error, 400)
    if not _has_manager_scope(manager_user_id):
        return MutationResult(False, "You are not assigned to any lab units for upload metadata management.", 403)
    key_status = check_field_key_availability(manager_user_id, dto.key)
    if not key_status.payload.get("available"):
        return MutationResult(
            False,
            "Upload metadata field key already exists.",
            key_status.status_code if not key_status.success else 400,
        )
    row = UploadMetadataFieldDefinition(
        scope=dto.scope.strip(),
        key=dto.key.strip(),
        label=dto.label.strip(),
        sctid=(dto.sctid or "").strip() or None,
        field_type=dto.field_type.strip(),
        selection_mode=_selection_mode(dto),
        options_json=_options(dto),
        description=dto.description,
        validation_regex=(dto.validation_regex or "").strip() or None,
        validation_error_message=(dto.validation_error_message or "").strip() or None,
        required_at_upload_default=dto.required_at_upload_default,
        editable_during_verification_default=dto.editable_during_verification_default,
        visible_to_grader_default=dto.visible_to_grader_default,
        is_pii_default=dto.is_pii_default,
        active=dto.active,
        created_by_user_id=manager_user_id,
        updated_by_user_id=manager_user_id,
    )
    with db_transaction_manager.transaction_scope() as db:
        db.add(row)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return MutationResult(False, "Upload metadata field key already exists.", 400)
        return MutationResult(True, "Upload metadata field created.", 201, payload={"field_definition": serialize_field_definition(row)})


def update_field_definition(manager_user_id: int, field_id: int, dto: FieldDefinitionInput) -> MutationResult:
    error = validate_field_definition_input(dto)
    if error:
        return MutationResult(False, error, 400)
    key_status = check_field_key_availability(manager_user_id, dto.key, exclude_id=field_id)
    if not key_status.payload.get("available"):
        return MutationResult(
            False,
            "Upload metadata field key already exists.",
            key_status.status_code if not key_status.success else 400,
        )
    with db_transaction_manager.transaction_scope() as db:
        row = _get_field_definition(db, manager_user_id, field_id)
        if row is None:
            return MutationResult(False, "Upload metadata field not found.", 404)
        row.scope = dto.scope.strip()
        row.key = dto.key.strip()
        row.label = dto.label.strip()
        row.sctid = (dto.sctid or "").strip() or None
        row.field_type = dto.field_type.strip()
        row.selection_mode = _selection_mode(dto)
        row.options_json = _options(dto)
        row.description = dto.description
        row.validation_regex = (dto.validation_regex or "").strip() or None
        row.validation_error_message = (dto.validation_error_message or "").strip() or None
        row.required_at_upload_default = dto.required_at_upload_default
        row.editable_during_verification_default = dto.editable_during_verification_default
        row.visible_to_grader_default = dto.visible_to_grader_default
        row.is_pii_default = dto.is_pii_default
        row.active = dto.active
        row.updated_by_user_id = manager_user_id
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return MutationResult(False, "Upload metadata field key already exists.", 400)
        return MutationResult(True, "Upload metadata field updated.", payload={"field_definition": serialize_field_definition(row)})


def set_field_definition_active(manager_user_id: int, field_id: int, active: bool) -> MutationResult:
    with db_transaction_manager.transaction_scope() as db:
        row = _get_field_definition(db, manager_user_id, field_id)
        if row is None:
            return MutationResult(False, "Upload metadata field not found.", 404)
        row.active = active
        row.updated_by_user_id = manager_user_id
        return MutationResult(True, "Upload metadata field activated." if active else "Upload metadata field deactivated.")


def check_field_key_availability(manager_user_id: int, key: str, *, exclude_id: int | None = None) -> MutationResult:
    normalized_key = str(key or "").strip()
    if not _has_manager_scope(manager_user_id):
        return MutationResult(
            False,
            "You are not assigned to any lab units for upload metadata management.",
            403,
            payload={"available": False, "message": "No upload metadata management scope."},
        )
    if not normalized_key:
        return MutationResult(True, "Field key is required.", payload={"available": False, "message": "Key is required."})
    if not _KEY_RE.match(normalized_key):
        return MutationResult(
            True,
            "Field key must start with a letter and use only letters, numbers, and underscores.",
            payload={"available": False, "message": "Start with a letter; use letters, numbers, and underscores."},
        )
    with db_transaction_manager.transaction_scope() as db:
        query = select(UploadMetadataFieldDefinition.id).where(UploadMetadataFieldDefinition.key == normalized_key)
        if exclude_id:
            query = query.where(UploadMetadataFieldDefinition.id != exclude_id)
        exists = db.execute(query.limit(1)).scalar_one_or_none() is not None
    if exists:
        return MutationResult(True, "Upload metadata field key already exists.", payload={"available": False, "message": "Already used by another field."})
    return MutationResult(True, "Upload metadata field key is available.", payload={"available": True, "message": "Key is available."})


def validate_field_definition_input(dto: FieldDefinitionInput) -> str | None:
    scope = dto.scope.strip()
    field_type = dto.field_type.strip()
    if scope not in SUPPORTED_FIELD_SCOPES:
        return "Field scope must be patient, encounter, image, document, or upload."
    if not dto.key or not _KEY_RE.match(dto.key.strip()):
        return "Field key is required, must be globally unique, must start with a letter, and may use only letters, numbers, and underscores."
    if not dto.label.strip():
        return "Field label is required."
    if field_type not in SUPPORTED_FIELD_TYPES:
        return "Unsupported field type."
    if field_type == "select":
        if _selection_mode(dto) not in SUPPORTED_SELECTION_MODES:
            return "Selection mode must be single or multiple."
        try:
            _options(dto)
        except ValueError as exc:
            return str(exc)
    elif dto.selection_mode:
        return "Selection mode is only valid for select fields."
    if dto.validation_regex:
        try:
            re.compile(dto.validation_regex)
        except re.error as exc:
            return f"Validation regex is invalid: {exc}."
    return None


def serialize_field_definition(row: UploadMetadataFieldDefinition) -> dict[str, Any]:
    return {
        "id": row.id,
        "scope": row.scope,
        "key": row.key,
        "label": row.label,
        "sctid": row.sctid,
        "type": row.field_type,
        "selection_mode": row.selection_mode,
        "options": row.options_json,
        "description": row.description,
        "validation_regex": row.validation_regex,
        "validation_error_message": row.validation_error_message,
        "required_at_upload_default": row.required_at_upload_default,
        "editable_during_verification_default": row.editable_during_verification_default,
        "visible_to_grader_default": row.visible_to_grader_default,
        "is_pii_default": row.is_pii_default,
        "active": row.active,
    }


def _has_manager_scope(manager_user_id: int) -> bool:
    return bool(manager_lab_unit_ids(manager_user_id))


def _get_field_definition(db, manager_user_id: int, field_id: int) -> UploadMetadataFieldDefinition | None:
    if not _has_manager_scope(manager_user_id):
        return None
    return db.get(UploadMetadataFieldDefinition, field_id)


def _selection_mode(dto: FieldDefinitionInput) -> str | None:
    return str(dto.selection_mode or "single").strip() if dto.field_type.strip() == "select" else None


def _options(dto: FieldDefinitionInput) -> list[dict[str, str]] | None:
    if dto.field_type.strip() != "select":
        return None
    return _normalize_options(dto.options_json or [], 1)


def _normalize_options(options: Any, idx: int) -> list[dict[str, str]]:
    if not isinstance(options, list):
        raise ValueError(f"options[{idx}] must be a list.")
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
            raise ValueError(f"options[{option_idx}] must be a string or object.")
        if not value:
            raise ValueError(f"options[{option_idx}] requires a value.")
        if value in seen_values:
            raise ValueError(f"options has duplicate value '{value}'.")
        seen_values.add(value)
        normalized.append({"value": value, "label": label or value})
    return normalized
