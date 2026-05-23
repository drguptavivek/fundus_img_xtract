"""JSON API routes for EncounterSetType administration."""
from __future__ import annotations

import json
import re
from typing import Any

from flask import Response, jsonify, request
from flask_login import current_user

from auth.roles import roles_required
from encounter_set_types import service as encounter_set_type_service
from upload_profiles.admin_service import MutationResult

from . import api_bp


@api_bp.route("/encounter-set-types", methods=["GET"])
@roles_required("admin", "local_admin", "data_manager")
def list_encounter_set_types():
    """List reusable encounter-set types visible to the manager."""
    rows = encounter_set_type_service.list_encounter_set_types(
        current_user.id,
        include_inactive=_bool_arg(request.args.get("include_inactive")),
    )
    return jsonify({"success": True, "encounter_set_types": rows})


@api_bp.route("/encounter-set-types", methods=["POST"])
@roles_required("admin", "local_admin", "data_manager")
def create_encounter_set_type():
    """Create an encounter-set type."""
    result = encounter_set_type_service.create_encounter_set_type(
        current_user.id,
        _input_from_request(),
    )
    return _json_result(result)


@api_bp.route("/encounter-set-types/<int:type_id>", methods=["GET"])
@roles_required("admin", "local_admin", "data_manager")
def get_encounter_set_type(type_id: int):
    """Read one encounter-set type."""
    return _json_result(encounter_set_type_service.get_encounter_set_type(current_user.id, type_id))


@api_bp.route("/encounter-set-types/<int:type_id>/schema", methods=["GET"])
@roles_required("admin", "local_admin", "data_manager")
def export_encounter_set_type_schema(type_id: int):
    """Export one encounter-set type schema as JSON."""
    result = encounter_set_type_service.export_encounter_set_type_schema(current_user.id, type_id)
    if not result.success:
        return _json_result(result)
    schema = result.payload["schema"]
    if _bool_arg(request.args.get("download")):
        filename = _safe_json_filename(result.payload["filename"])
        return Response(
            json.dumps(schema, indent=2, sort_keys=True) + "\n",
            mimetype="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    return jsonify({"success": True, "schema": schema})


@api_bp.route("/encounter-set-types/<int:type_id>", methods=["PATCH", "POST"])
@roles_required("admin", "local_admin", "data_manager")
def update_encounter_set_type(type_id: int):
    """Update an encounter-set type."""
    result = encounter_set_type_service.update_encounter_set_type(
        current_user.id,
        type_id,
        _input_from_request(),
    )
    return _json_result(result)


@api_bp.route("/encounter-set-types/<int:type_id>/activate", methods=["POST"])
@roles_required("admin", "local_admin", "data_manager")
def activate_encounter_set_type(type_id: int):
    """Activate an encounter-set type."""
    return _json_result(encounter_set_type_service.set_encounter_set_type_active(current_user.id, type_id, True))


@api_bp.route("/encounter-set-types/<int:type_id>/deactivate", methods=["POST"])
@roles_required("admin", "local_admin", "data_manager")
def deactivate_encounter_set_type(type_id: int):
    """Deactivate an encounter-set type."""
    return _json_result(encounter_set_type_service.set_encounter_set_type_active(current_user.id, type_id, False))


@api_bp.route("/encounter-set-types/<int:type_id>/delete", methods=["POST"])
@roles_required("admin", "local_admin", "data_manager")
def delete_encounter_set_type(type_id: int):
    """Delete an encounter-set type when it is not linked to upload profiles."""
    return _json_result(encounter_set_type_service.delete_encounter_set_type(current_user.id, type_id))


@api_bp.route("/encounter-set-types/<int:type_id>", methods=["DELETE"])
@roles_required("admin", "local_admin", "data_manager")
def delete_encounter_set_type_rest(type_id: int):
    """REST delete alias for API clients."""
    return _json_result(encounter_set_type_service.delete_encounter_set_type(current_user.id, type_id))


def _input_from_request() -> encounter_set_type_service.EncounterSetTypeInput:
    data = _request_data()
    return encounter_set_type_service.EncounterSetTypeInput(
        name=str(data.get("name") or "").strip(),
        code=str(data.get("code") or "").strip(),
        description=(str(data.get("description")).strip() if data.get("description") is not None else None) or None,
        metadata_schema_json=data.get("metadata_schema_json") or {"fields": []},
        asset_rules_json=data.get("asset_rules_json"),
        active=_bool_value(data.get("active"), default=True),
    )


def _request_data() -> dict[str, Any]:
    if request.is_json:
        payload = request.get_json(silent=True)
        return payload if isinstance(payload, dict) else {}
    data: dict[str, Any] = dict(request.form.items())
    if "metadata_schema_json" in data:
        data["metadata_schema_json"] = request.form.get("metadata_schema_json")
    if "asset_rules_json" in data:
        data["asset_rules_json"] = request.form.get("asset_rules_json")
    return data


def _json_result(result: MutationResult):
    payload = {
        "success": result.success,
        "message": result.message,
    }
    if not result.success:
        payload["error"] = result.message
    if result.payload:
        payload.update(result.payload)
    return jsonify(payload), result.status_code


def _safe_json_filename(filename: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", filename).strip("._")
    if not cleaned:
        return "encounter_set_type_schema.json"
    return cleaned if cleaned.endswith(".json") else f"{cleaned}.json"


def _bool_arg(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _bool_value(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}
