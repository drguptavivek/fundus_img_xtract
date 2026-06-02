"""JSON API routes for reusable upload metadata field definitions."""
from __future__ import annotations

from typing import Any

from flask import jsonify, request
from flask_login import current_user

from auth.roles import roles_required
from upload_metadata import service as upload_metadata_service
from upload_profiles.admin_service import MutationResult

from . import api_bp


@api_bp.route("/upload-metadata/field-definitions", methods=["GET"])
@roles_required("admin", "local_admin", "data_manager")
def list_upload_metadata_field_definitions():
    rows = upload_metadata_service.list_field_definitions(
        current_user.id,
        include_inactive=_bool_arg(request.args.get("include_inactive")),
    )
    return jsonify({"success": True, "field_definitions": rows})


@api_bp.route("/upload-metadata/field-definitions", methods=["POST"])
@roles_required("admin", "local_admin", "data_manager")
def create_upload_metadata_field_definition():
    return _json_result(upload_metadata_service.create_field_definition(current_user.id, _input_from_request()))


@api_bp.route("/upload-metadata/field-definitions/key-availability", methods=["GET"])
@roles_required("admin", "local_admin", "data_manager")
def check_upload_metadata_field_key():
    exclude_id = _int_arg(request.args.get("exclude_id"))
    result = upload_metadata_service.check_field_key_availability(
        current_user.id,
        str(request.args.get("key") or "").strip(),
        exclude_id=exclude_id,
    )
    return _json_result(result)


@api_bp.route("/upload-metadata/field-definitions/<int:field_id>", methods=["PATCH", "POST"])
@roles_required("admin", "local_admin", "data_manager")
def update_upload_metadata_field_definition(field_id: int):
    return _json_result(upload_metadata_service.update_field_definition(current_user.id, field_id, _input_from_request()))


@api_bp.route("/upload-metadata/field-definitions/<int:field_id>/activate", methods=["POST"])
@roles_required("admin", "local_admin", "data_manager")
def activate_upload_metadata_field_definition(field_id: int):
    return _json_result(upload_metadata_service.set_field_definition_active(current_user.id, field_id, True))


@api_bp.route("/upload-metadata/field-definitions/<int:field_id>/deactivate", methods=["POST"])
@roles_required("admin", "local_admin", "data_manager")
def deactivate_upload_metadata_field_definition(field_id: int):
    return _json_result(upload_metadata_service.set_field_definition_active(current_user.id, field_id, False))


def _input_from_request() -> upload_metadata_service.FieldDefinitionInput:
    data = _request_data()
    return upload_metadata_service.FieldDefinitionInput(
        scope=str(data.get("scope") or "").strip(),
        key=str(data.get("key") or "").strip(),
        label=str(data.get("label") or "").strip(),
        sctid=(str(data.get("sctid")).strip() if data.get("sctid") is not None else None) or None,
        field_type=str(data.get("field_type") or data.get("type") or "").strip(),
        selection_mode=(str(data.get("selection_mode")).strip() if data.get("selection_mode") is not None else None),
        options_json=data.get("options_json") or data.get("options") or [],
        description=(str(data.get("description")).strip() if data.get("description") is not None else None) or None,
        validation_regex=(str(data.get("validation_regex")).strip() if data.get("validation_regex") is not None else None) or None,
        validation_error_message=(str(data.get("validation_error_message")).strip() if data.get("validation_error_message") is not None else None) or None,
        required_at_upload_default=_bool_value(data.get("required_at_upload_default"), default=False),
        editable_during_verification_default=_bool_value(
            data.get("editable_during_verification_default", data.get("required_for_verification_default")),
            default=False,
        ),
        visible_to_grader_default=_bool_value(data.get("visible_to_grader_default"), default=False),
        is_pii_default=_bool_value(data.get("is_pii_default"), default=False),
        active=_bool_value(data.get("active"), default=True),
    )


def _request_data() -> dict[str, Any]:
    if request.is_json:
        payload = request.get_json(silent=True)
        return payload if isinstance(payload, dict) else {}
    data: dict[str, Any] = dict(request.form.items())
    if "options_json" in data:
        options_text = request.form.get("options_json") or ""
        data["options_json"] = [item.strip() for item in options_text.splitlines() if item.strip()]
    return data


def _json_result(result: MutationResult):
    payload = {"success": result.success, "message": result.message}
    if not result.success:
        payload["error"] = result.message
    if result.payload:
        payload.update(result.payload)
    return jsonify(payload), result.status_code


def _bool_arg(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _int_arg(value: str | None) -> int | None:
    try:
        parsed = int(str(value or "").strip())
    except ValueError:
        return None
    return parsed if parsed > 0 else None


def _bool_value(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}
