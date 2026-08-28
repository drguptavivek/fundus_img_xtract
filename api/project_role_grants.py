"""REST API for project-scoped application role grants."""
from __future__ import annotations

from dataclasses import asdict

from flask import jsonify, request
from flask_login import current_user, login_required

from data_authorization.dto import ProjectRoleGrantInput
from data_authorization.exceptions import ProjectGrantPermissionDenied, ProjectGrantValidationError
from data_authorization.service import (
    deactivate_project_role_grant,
    list_project_role_grants,
    replace_project_role_grants,
    upsert_project_role_grant,
)
from db_transaction_manager import transaction_scope

from . import api_bp


def _optional_int(value) -> int | None:
    if value in {None, ""}:
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ProjectGrantValidationError("Scope identifiers must be integers.") from exc


def _required_int(value, field_name: str) -> int:
    parsed = _optional_int(value)
    if parsed is None:
        raise ProjectGrantValidationError(f"{field_name} is required.")
    return parsed


def _grant_input(project_id: int) -> ProjectRoleGrantInput:
    payload = request.get_json(silent=True) if request.is_json else request.form
    active_value = payload.get("active", True)
    active = active_value is True or str(active_value).strip().lower() in {"1", "true", "yes", "on"}
    return ProjectRoleGrantInput(
        project_id=project_id,
        user_id=_required_int(payload.get("user_id"), "user_id"),
        role_name=str(payload.get("role_name") or "").strip(),
        scope_type=str(payload.get("scope_type") or "").strip(),
        lab_unit_id=_optional_int(payload.get("lab_unit_id")),
        active=active,
    )


def _scope_values(payload) -> tuple[str, int | None]:
    scope_key = str(payload.get("scope_key") or "").strip()
    if scope_key:
        if scope_key == "project":
            return "project", None
        try:
            scope_type, raw_id = scope_key.split(":", 1)
            scope_id = int(raw_id)
        except (TypeError, ValueError) as exc:
            raise ProjectGrantValidationError("Select a valid project scope.") from exc
        if scope_type == "lab_unit":
            return scope_type, scope_id
        raise ProjectGrantValidationError("Select a valid project scope.")
    return (
        str(payload.get("scope_type") or "").strip(),
        _optional_int(payload.get("lab_unit_id")),
    )


@api_bp.route("/projects/<int:project_id>/role-grants", methods=["GET", "POST", "PUT"])
@login_required
def project_role_grants(project_id: int):
    """List or upsert role-catalog-backed membership grants for one project."""
    try:
        with transaction_scope() as db:
            updated = None
            if request.method != "GET":
                payload = request.get_json(silent=True) if request.is_json else request.form
                role_names = payload.get("role_names") if request.is_json else request.form.getlist("role_names")
                if role_names is not None:
                    if not isinstance(role_names, list):
                        raise ProjectGrantValidationError("role_names must be a list.")
                    scope_type, lab_unit_id = _scope_values(payload)
                    updated = replace_project_role_grants(
                        db,
                        actor=current_user,
                        project_id=project_id,
                        user_id=_required_int(payload.get("user_id"), "user_id"),
                        role_names=role_names,
                        scope_type=scope_type,
                        lab_unit_id=lab_unit_id,
                        original_scope_type=(str(payload.get("original_scope_type") or "").strip() or None),
                        original_lab_unit_id=_optional_int(payload.get("original_lab_unit_id")),
                    )
                else:
                    updated = upsert_project_role_grant(
                        db,
                        actor=current_user,
                        data=_grant_input(project_id),
                    )
            grants = list_project_role_grants(db, actor=current_user, project_id=project_id)
            return jsonify({
                "success": True,
                "data": {
                    "project_id": project_id,
                    "updated": (
                        [asdict(item) for item in updated]
                        if isinstance(updated, tuple)
                        else asdict(updated) if updated else None
                    ),
                    "grants": [asdict(grant) for grant in grants],
                },
            })
    except ProjectGrantPermissionDenied as exc:
        return jsonify({"success": False, "error": str(exc)}), 403
    except ProjectGrantValidationError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400


@api_bp.route(
    "/projects/<int:project_id>/role-grants/<int:grant_id>",
    methods=["DELETE", "POST"],
)
@login_required
def remove_project_role_grant(project_id: int, grant_id: int):
    """Deactivate one project role grant; POST supports HTML/HTMX forms."""
    try:
        with transaction_scope() as db:
            removed = deactivate_project_role_grant(
                db,
                actor=current_user,
                project_id=project_id,
                grant_id=grant_id,
            )
            return jsonify({"success": True, "data": {"removed": asdict(removed)}})
    except ProjectGrantPermissionDenied as exc:
        return jsonify({"success": False, "error": str(exc)}), 403
    except ProjectGrantValidationError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
