"""Persistent, versioned EncounterSet CSV mapper lifecycle."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from sqlalchemy import select

import db_transaction_manager
from auth.utils import utcnow
from encounter_set_types.models import (
    EncounterSetImportMapperAudit,
    EncounterSetImportMapperRevision,
    EncounterSetType,
)
from upload_profiles.admin_service import MutationResult
from upload_profiles.service import manager_lab_unit_ids

STATUSES = {"draft", "finalized", "retired"}
RESERVED_ROLES = {"encounter_identity", "capture_datetime", "clinical_image_filename"}
EYE_SUFFIX = re.compile(r"^(.+)_(od|os|rt|lt|re|le)$", re.IGNORECASE)
EYE_FAMILIES = ({"od", "os"}, {"rt", "lt"}, {"re", "le"})


@dataclass(frozen=True)
class MapperInput:
    name: str
    source_headers: list[str]
    mapping: dict[str, Any]


def schema_fingerprint(schema: dict[str, Any]) -> str:
    encoded = json.dumps(schema or {"fields": []}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def header_fingerprint(headers: list[str]) -> str:
    return hashlib.sha256("\x1f".join(headers).encode("utf-8")).hexdigest()


def list_revisions(user_id: int, type_id: int) -> MutationResult:
    with db_transaction_manager.transaction_scope() as db:
        encounter_type = _scoped_type(db, user_id, type_id)
        if encounter_type is None:
            return MutationResult(False, "Encounter-set type not found.", 404)
        rows = db.execute(
            select(EncounterSetImportMapperRevision)
            .where(EncounterSetImportMapperRevision.encounter_set_type_id == type_id)
            .order_by(EncounterSetImportMapperRevision.created_at.desc())
        ).scalars().all()
        return MutationResult(True, "Mapper revisions found.", payload={"mapper_revisions": [_serialize(row) for row in rows]})


def create_draft(user_id: int, type_id: int, dto: MapperInput) -> MutationResult:
    with db_transaction_manager.transaction_scope() as db:
        encounter_type = _scoped_type(db, user_id, type_id)
        if encounter_type is None:
            return MutationResult(False, "Encounter-set type not found.", 404)
        error, normalized = _validate(encounter_type, dto)
        if error:
            return MutationResult(False, error, 400)
        row = EncounterSetImportMapperRevision(
            mapper_uuid=str(uuid4()), encounter_set_type_id=type_id, name=dto.name.strip(), revision=1,
            status="draft", schema_fingerprint=schema_fingerprint(encounter_type.metadata_schema_json),
            source_header_fingerprint=header_fingerprint(dto.source_headers), source_headers_json=dto.source_headers,
            mapping_json=normalized, created_by_user_id=user_id, updated_by_user_id=user_id,
        )
        db.add(row); db.flush(); _audit(db, row, "created", user_id)
        return MutationResult(True, "Mapper draft created.", 201, {"mapper_revision": _serialize(row)})


def update_draft(user_id: int, revision_id: int, dto: MapperInput) -> MutationResult:
    with db_transaction_manager.transaction_scope() as db:
        row = _scoped_revision(db, user_id, revision_id)
        if row is None:
            return MutationResult(False, "Mapper revision not found.", 404)
        if row.status != "draft":
            return MutationResult(False, "Finalized and retired mapper revisions are immutable; clone one to make changes.", 409)
        error, normalized = _validate(row.encounter_set_type, dto)
        if error:
            return MutationResult(False, error, 400)
        row.name = dto.name.strip(); row.source_headers_json = dto.source_headers
        row.source_header_fingerprint = header_fingerprint(dto.source_headers); row.mapping_json = normalized
        row.schema_fingerprint = schema_fingerprint(row.encounter_set_type.metadata_schema_json)
        row.updated_by_user_id = user_id; row.updated_at = utcnow(); _audit(db, row, "updated", user_id)
        return MutationResult(True, "Mapper draft updated.", payload={"mapper_revision": _serialize(row)})


def finalize(user_id: int, revision_id: int) -> MutationResult:
    with db_transaction_manager.transaction_scope() as db:
        row = _scoped_revision(db, user_id, revision_id)
        if row is None: return MutationResult(False, "Mapper revision not found.", 404)
        if row.status != "draft": return MutationResult(False, "Only a draft mapper can be finalized.", 409)
        if row.schema_fingerprint != schema_fingerprint(row.encounter_set_type.metadata_schema_json):
            return MutationResult(False, "EncounterSetType schema changed. Clone or update the draft against the current schema before finalizing.", 409)
        error, normalized = _validate(row.encounter_set_type, MapperInput(row.name, row.source_headers_json, row.mapping_json))
        if error: return MutationResult(False, error, 400)
        row.mapping_json = normalized; row.status = "finalized"; row.finalized_at = utcnow()
        row.updated_at = utcnow(); row.updated_by_user_id = user_id; _audit(db, row, "finalized", user_id)
        return MutationResult(True, "Mapper revision finalized and is now immutable.", payload={"mapper_revision": _serialize(row)})


def clone(user_id: int, revision_id: int) -> MutationResult:
    with db_transaction_manager.transaction_scope() as db:
        source = _scoped_revision(db, user_id, revision_id)
        if source is None: return MutationResult(False, "Mapper revision not found.", 404)
        existing_revisions = db.execute(select(EncounterSetImportMapperRevision).where(
            EncounterSetImportMapperRevision.mapper_uuid == source.mapper_uuid).with_for_update()).scalars().all()
        next_revision = max((item.revision for item in existing_revisions), default=0)
        row = EncounterSetImportMapperRevision(
            mapper_uuid=source.mapper_uuid, encounter_set_type_id=source.encounter_set_type_id,
            name=source.name, revision=next_revision + 1, status="draft",
            schema_fingerprint=schema_fingerprint(source.encounter_set_type.metadata_schema_json),
            source_header_fingerprint=source.source_header_fingerprint,
            source_headers_json=list(source.source_headers_json), mapping_json=dict(source.mapping_json),
            cloned_from_revision_id=source.id, created_by_user_id=user_id, updated_by_user_id=user_id,
        )
        db.add(row); db.flush(); _audit(db, row, "cloned", user_id)
        return MutationResult(True, "Editable mapper draft cloned.", 201, {"mapper_revision": _serialize(row)})


def retire(user_id: int, revision_id: int) -> MutationResult:
    with db_transaction_manager.transaction_scope() as db:
        row = _scoped_revision(db, user_id, revision_id)
        if row is None: return MutationResult(False, "Mapper revision not found.", 404)
        if row.status != "finalized": return MutationResult(False, "Only a finalized mapper can be retired.", 409)
        row.status = "retired"; row.retired_at = utcnow(); row.updated_at = utcnow(); row.updated_by_user_id = user_id
        _audit(db, row, "retired", user_id)
        return MutationResult(True, "Mapper revision retired. Existing imports may continue to reference it.", payload={"mapper_revision": _serialize(row)})


def delete_draft(user_id: int, revision_id: int) -> MutationResult:
    with db_transaction_manager.transaction_scope() as db:
        row = _scoped_revision(db, user_id, revision_id)
        if row is None: return MutationResult(False, "Mapper revision not found.", 404)
        if row.status != "draft" or row.use_count:
            return MutationResult(False, "Only an unused draft mapper revision can be deleted.", 409)
        _audit(db, row, "deleted", user_id); db.delete(row)
        return MutationResult(True, "Unused mapper draft deleted.")


def _validate(encounter_type: EncounterSetType, dto: MapperInput) -> tuple[str | None, dict[str, Any]]:
    name = dto.name.strip()
    if not name or len(name) > 150: return "Mapper name is required and must be at most 150 characters.", {}
    headers = [str(value).strip() for value in dto.source_headers]
    if not headers or any(not value for value in headers) or len(headers) != len(set(headers)):
        return "Source headers must be a non-empty unique list.", {}
    mapping = dto.mapping if isinstance(dto.mapping, dict) else {}
    columns = mapping.get("column_mappings", []); reserved = mapping.get("reserved_columns", [])
    excluded = mapping.get("excluded_columns", []); defaults = mapping.get("defaults", {})
    value_mappings = mapping.get("value_mappings", {})
    if not all(isinstance(value, list) for value in (columns, reserved, excluded)):
        return "Column mappings, reserved columns, and excluded columns must be lists.", {}
    if not isinstance(defaults, dict) or not isinstance(value_mappings, dict):
        return "Defaults and value mappings must be objects.", {}
    classified: list[str] = []
    for item in columns + reserved + excluded:
        if not isinstance(item, dict) or not str(item.get("source_column") or "").strip():
            return "Every mapper entry requires a source_column.", {}
        classified.append(str(item["source_column"]).strip())
    unknown = sorted(set(classified) - set(headers)); duplicate = sorted(k for k in set(classified) if classified.count(k) > 1)
    missing = sorted(set(headers) - set(classified))
    if unknown: return f"Unknown source column(s): {', '.join(unknown)}.", {}
    if duplicate: return f"Source column(s) classified more than once: {', '.join(duplicate)}.", {}
    if missing: return f"Every source header must be mapped, reserved, or excluded. Missing: {', '.join(missing)}.", {}
    field_map = {str(f.get("key")): f for f in (encounter_type.metadata_schema_json or {}).get("fields", []) if isinstance(f, dict)}
    mapped_keys: set[str] = set()
    eye_families: dict[str, set[str]] = {}
    for item in columns:
        key = str(item.get("canonical_key") or ""); scope = str(item.get("scope") or "")
        if key not in field_map: return f"Canonical field '{key}' is not defined by this EncounterSetType.", {}
        if scope != str(field_map[key].get("scope")): return f"Scope for '{key}' must be '{field_map[key].get('scope')}'.", {}
        laterality = item.get("laterality")
        if laterality not in (None, "OD", "OS"): return "Laterality must be OD or OS.", {}
        match = EYE_SUFFIX.match(str(item["source_column"]));
        if laterality and not match: return f"Eye-specific column '{item['source_column']}' must use _od/_os, _rt/_lt, or _re/_le.", {}
        if match: eye_families.setdefault(match.group(1).lower(), set()).add(match.group(2).lower())
        mapped_keys.add(key)
    for suffixes in eye_families.values():
        if sum(bool(suffixes & family) for family in EYE_FAMILIES) > 1:
            return "An eye field cannot mix _od/_os, _rt/_lt, and _re/_le conventions.", {}
    identities = 0
    for item in reserved:
        if item.get("role") not in RESERVED_ROLES: return f"Unsupported reserved role '{item.get('role')}'.", {}
        identities += item.get("role") == "encounter_identity"
        if item.get("role") == "clinical_image_filename" and item.get("laterality") not in {"OD", "OS"}:
            return "Clinical image filename columns require OD or OS laterality.", {}
    if identities != 1: return "Exactly one encounter_identity source column is required.", {}
    unknown_defaults = sorted(set(defaults) - set(field_map)); unknown_values = sorted(set(value_mappings) - set(headers))
    if unknown_defaults: return f"Default target field(s) are not in the schema: {', '.join(unknown_defaults)}.", {}
    if unknown_values: return f"Value mappings reference unknown source column(s): {', '.join(unknown_values)}.", {}
    required = {key for key, field in field_map.items() if field.get("required_at_upload") and key != "laterality"}
    unmet = sorted(required - mapped_keys - set(defaults))
    if unmet: return f"Required field(s) need a source mapping or default: {', '.join(unmet)}.", {}
    normalized = {"version": 1, "column_mappings": columns, "reserved_columns": reserved,
                  "excluded_columns": excluded, "defaults": defaults, "value_mappings": value_mappings}
    return None, normalized


def _scoped_type(db, user_id: int, type_id: int):
    if not manager_lab_unit_ids(user_id): return None
    return db.get(EncounterSetType, type_id)


def _scoped_revision(db, user_id: int, revision_id: int):
    if not manager_lab_unit_ids(user_id): return None
    return db.execute(select(EncounterSetImportMapperRevision).where(
        EncounterSetImportMapperRevision.id == revision_id)).scalar_one_or_none()


def _serialize(row: EncounterSetImportMapperRevision) -> dict[str, Any]:
    return {"id": row.id, "mapper_uuid": row.mapper_uuid, "encounter_set_type_id": row.encounter_set_type_id,
            "name": row.name, "revision": row.revision, "status": row.status,
            "schema_fingerprint": row.schema_fingerprint, "source_header_fingerprint": row.source_header_fingerprint,
            "source_headers": row.source_headers_json, "mapping": row.mapping_json, "use_count": row.use_count,
            "cloned_from_revision_id": row.cloned_from_revision_id,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            "finalized_at": row.finalized_at.isoformat() if row.finalized_at else None,
            "retired_at": row.retired_at.isoformat() if row.retired_at else None}


def _audit(db, row: EncounterSetImportMapperRevision, action: str, user_id: int) -> None:
    db.add(EncounterSetImportMapperAudit(mapper_revision_id=row.id, mapper_uuid=row.mapper_uuid,
        revision=row.revision, action=action, actor_user_id=user_id,
        snapshot_json={"name": row.name, "status": row.status, "schema_fingerprint": row.schema_fingerprint,
                       "source_header_fingerprint": row.source_header_fingerprint, "mapping": row.mapping_json}))
