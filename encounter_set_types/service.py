"""Service layer for EncounterSetType administration."""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any

import db_transaction_manager
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from encounter_set_types.models import EncounterSetType
from models import Disease, Project
from upload_profiles.admin_service import MutationResult
from upload_profiles.models import UploadProfile
from upload_profiles.service import manager_lab_unit_ids


SUPPORTED_FIELD_TYPES = {
    "text",
    "textarea",
    "integer",
    "decimal",
    "date",
    "datetime",
    "boolean",
    "select",
    "phone",
    "email",
}
SUPPORTED_SCOPES = {"encounter", "image"}
SUPPORTED_SELECTION_MODES = {"single", "multiple"}
_KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_CODE_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


@dataclass
class EncounterSetTypeInput:
    project_id: int | None
    name: str
    code: str
    target_scheme_id: int | None
    metadata_schema_json: dict[str, Any]
    description: str | None = None
    active: bool = True


def list_encounter_set_types(
    manager_user_id: int,
    *,
    project_id: int | None = None,
    include_inactive: bool = False,
) -> list[dict[str, Any]]:
    """List encounter-set types in the manager's upload-profile project scope."""
    with db_transaction_manager.transaction_scope() as db:
        scoped_project_ids = _manager_project_ids(db, manager_user_id)
        if not scoped_project_ids:
            return []
        query = (
            select(EncounterSetType)
            .where(EncounterSetType.project_id.in_(scoped_project_ids))
            .options(
                selectinload(EncounterSetType.project),
                selectinload(EncounterSetType.target_scheme),
            )
            .order_by(EncounterSetType.project_id, EncounterSetType.active.desc(), EncounterSetType.name)
        )
        if project_id is not None:
            query = query.where(EncounterSetType.project_id == project_id)
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


def create_encounter_set_type(manager_user_id: int, dto: EncounterSetTypeInput) -> MutationResult:
    error = validate_encounter_set_type_input(dto)
    if error:
        return MutationResult(False, error, 400)
    with db_transaction_manager.transaction_scope() as db:
        if not _can_manage_project(db, manager_user_id, dto.project_id):
            return MutationResult(False, "Project not found in your upload-profile scope.", 404)
        if db.get(Disease, dto.target_scheme_id) is None:
            return MutationResult(False, "Target scheme not found.", 404)
        row = EncounterSetType(
            project_id=dto.project_id,
            name=dto.name.strip(),
            code=dto.code.strip(),
            description=dto.description,
            target_scheme_id=dto.target_scheme_id,
            metadata_schema_json=normalize_metadata_schema(dto.metadata_schema_json),
            active=dto.active,
            created_by_user_id=manager_user_id,
            updated_by_user_id=manager_user_id,
        )
        db.add(row)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return MutationResult(False, "Encounter-set type code already exists for this project.", 400)
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
        if not _can_manage_project(db, manager_user_id, dto.project_id):
            return MutationResult(False, "Project not found in your upload-profile scope.", 404)
        if db.get(Disease, dto.target_scheme_id) is None:
            return MutationResult(False, "Target scheme not found.", 404)
        row.project_id = dto.project_id
        row.name = dto.name.strip()
        row.code = dto.code.strip()
        row.description = dto.description
        row.target_scheme_id = dto.target_scheme_id
        row.metadata_schema_json = normalize_metadata_schema(dto.metadata_schema_json)
        row.active = dto.active
        row.updated_by_user_id = manager_user_id
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return MutationResult(False, "Encounter-set type code already exists for this project.", 400)
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


def validate_encounter_set_type_input(dto: EncounterSetTypeInput) -> str | None:
    if not dto.project_id:
        return "Project is required."
    if not (dto.name or "").strip():
        return "Encounter-set type name is required."
    if not (dto.code or "").strip():
        return "Encounter-set type code is required."
    if not _CODE_RE.match(dto.code.strip()):
        return "Encounter-set type code may contain only letters, numbers, underscores, hyphens, and dots."
    if not dto.target_scheme_id:
        return "Target scheme is required."
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
    seen: set[tuple[str, str]] = set()
    for idx, field in enumerate(fields, start=1):
        if not isinstance(field, dict):
            raise ValueError(f"metadata_schema_json.fields[{idx}] must be an object.")
        normalized = _normalize_field(field, idx)
        identity = (normalized["scope"], normalized["key"])
        if identity in seen:
            raise ValueError(
                f"metadata_schema_json.fields[{idx}] duplicates key '{normalized['key']}' in scope '{normalized['scope']}'."
            )
        seen.add(identity)
        normalized_fields.append(normalized)
    return {"fields": normalized_fields}


def serialize_encounter_set_type(row: EncounterSetType) -> dict[str, Any]:
    return {
        "id": row.id,
        "project_id": row.project_id,
        "project_title": row.project.title if row.project else None,
        "project_code": row.project.code if row.project else None,
        "name": row.name,
        "code": row.code,
        "description": row.description,
        "target_scheme_id": row.target_scheme_id,
        "target_scheme_name": row.target_scheme.name if row.target_scheme else None,
        "metadata_schema_json": row.metadata_schema_json or {"fields": []},
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
        raise ValueError(f"metadata_schema_json.fields[{idx}] scope must be encounter or image.")
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

    return {
        "key": key,
        "label": label,
        "scope": scope,
        "type": field_type,
        "selection_mode": selection_mode,
        "options": options,
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


def _manager_project_ids(db, manager_user_id: int) -> set[int]:
    scoped_lab_ids = manager_lab_unit_ids(manager_user_id)
    if not scoped_lab_ids:
        return set()
    return {
        row[0]
        for row in db.execute(
            select(UploadProfile.project_id).where(
                UploadProfile.lab_unit_id.in_(scoped_lab_ids),
                UploadProfile.active.is_(True),
            )
        ).all()
    }


def _can_manage_project(db, manager_user_id: int, project_id: int | None) -> bool:
    if not project_id or db.get(Project, project_id) is None:
        return False
    scoped_lab_ids = manager_lab_unit_ids(manager_user_id)
    if not scoped_lab_ids:
        return False
    return (
        db.execute(
            select(UploadProfile.id).where(
                UploadProfile.project_id == project_id,
                UploadProfile.lab_unit_id.in_(scoped_lab_ids),
                UploadProfile.active.is_(True),
            )
        ).first()
        is not None
    )


def _get_scoped_type(db, manager_user_id: int, type_id: int) -> EncounterSetType | None:
    scoped_project_ids = _manager_project_ids(db, manager_user_id)
    if not scoped_project_ids:
        return None
    return (
        db.execute(
            select(EncounterSetType)
            .where(
                EncounterSetType.id == type_id,
                EncounterSetType.project_id.in_(scoped_project_ids),
            )
            .options(
                selectinload(EncounterSetType.project),
                selectinload(EncounterSetType.target_scheme),
            )
        )
        .scalars()
        .one_or_none()
    )
