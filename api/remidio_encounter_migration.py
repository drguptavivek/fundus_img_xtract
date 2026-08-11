"""REST API for correcting wrongly routed Remidio API EncounterSets.

All endpoints require the admin role. Mutating requests use the application's
standard CSRF protection and therefore require ``X-CSRFToken``.
"""
from __future__ import annotations

from datetime import datetime

from flask import jsonify, request
from flask_login import current_user

from auth.roles import roles_required
from db_transaction_manager import transaction_scope
from remidio_encounter_migration import service
from remidio_encounter_migration.exceptions import RemidioEncounterMigrationError

from . import api_bp


@api_bp.route("/remidio-api/encounter-migrations/projects", methods=["GET"])
@roles_required("admin")
def remidio_migration_projects():
    with transaction_scope() as db:
        return jsonify({"success": True, "projects": [row.to_dict() for row in service.list_projects(db)]})


@api_bp.route("/remidio-api/encounter-migrations/source-dates", methods=["GET"])
@roles_required("admin")
def remidio_migration_source_dates():
    try:
        source_project_id = _required_int(request.args.get("source_project_id"), "source_project_id")
        with transaction_scope() as db:
            rows = service.list_capture_dates(db, source_project_id=source_project_id)
            return jsonify({"success": True, "dates": [row.to_dict() for row in rows]})
    except RemidioEncounterMigrationError as exc:
        return _error(exc)


@api_bp.route("/remidio-api/encounter-migrations/encounters", methods=["GET"])
@roles_required("admin")
def remidio_migration_encounters():
    try:
        source_project_id = _required_int(request.args.get("source_project_id"), "source_project_id")
        capture_date = _required_date(request.args.get("capture_date"))
        with transaction_scope() as db:
            rows = service.list_encounters(db, source_project_id=source_project_id, capture_date=capture_date)
            return jsonify({"success": True, "encounters": [row.to_dict() for row in rows]})
    except RemidioEncounterMigrationError as exc:
        return _error(exc)


@api_bp.route("/remidio-api/encounter-migrations/preview", methods=["POST"])
@roles_required("admin")
def remidio_migration_preview():
    try:
        payload = _json_payload()
        with transaction_scope() as db:
            preview = service.preview_migration(db, **_migration_args(payload))
            return jsonify({"success": True, "preview": preview.to_dict()})
    except RemidioEncounterMigrationError as exc:
        return _error(exc)


@api_bp.route("/remidio-api/encounter-migrations", methods=["POST"])
@roles_required("admin")
def remidio_migration_apply():
    try:
        payload = _json_payload()
        confirmation_token = str(payload.get("confirmation_token") or "").strip()
        if not confirmation_token:
            raise RemidioEncounterMigrationError("confirmation_token is required.")
        with transaction_scope() as db:
            result = service.apply_migration(
                db,
                actor_user_id=current_user.id,
                confirmation_token=confirmation_token,
                ip_address=request.remote_addr,
                user_agent=request.headers.get("User-Agent"),
                **_migration_args(payload),
            )
            return jsonify({"success": True, "result": result.to_dict()})
    except RemidioEncounterMigrationError as exc:
        return _error(exc)


def _migration_args(payload: dict) -> dict:
    raw_ids = payload.get("encounter_ids")
    if not isinstance(raw_ids, list):
        raise RemidioEncounterMigrationError("encounter_ids must be an array.")
    try:
        encounter_ids = tuple(_required_int(value, "encounter_ids") for value in raw_ids)
    except (TypeError, ValueError) as exc:
        raise RemidioEncounterMigrationError("encounter_ids must contain integers.") from exc
    return {
        "source_project_id": _required_int(payload.get("source_project_id"), "source_project_id"),
        "target_project_id": _required_int(payload.get("target_project_id"), "target_project_id"),
        "capture_date": _required_date(payload.get("capture_date")),
        "encounter_ids": encounter_ids,
    }


def _json_payload() -> dict:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise RemidioEncounterMigrationError("A JSON object request body is required.")
    return payload


def _required_int(value, field: str) -> int:
    if isinstance(value, bool):
        raise RemidioEncounterMigrationError(f"{field} must be an integer.")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise RemidioEncounterMigrationError(f"{field} is required and must be an integer.") from exc
    if parsed < 1:
        raise RemidioEncounterMigrationError(f"{field} must be a positive integer.")
    return parsed


def _required_date(value):
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except (TypeError, ValueError) as exc:
        raise RemidioEncounterMigrationError("capture_date is required in YYYY-MM-DD format.") from exc


def _error(exc: RemidioEncounterMigrationError):
    return jsonify({
        "success": False,
        "error": {"message": exc.message, "details": exc.details},
    }), exc.status_code
