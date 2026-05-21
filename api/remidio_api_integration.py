"""API routes for Remidio gateway configuration and metadata pulls."""

from __future__ import annotations

import logging

from flask import jsonify, request
from sqlalchemy.exc import IntegrityError

from auth.roles import roles_required
from db_transaction_manager import transaction_scope
from remidio_api_integration import service
from remidio_api_integration.errors import RemidioIntegrationError
from utils.log_sanitize import sanitize_log_value

from . import api_bp


logger = logging.getLogger("api.remidio_api_integration")
REMIDIO_ROLES = ("admin", "data_manager")


@api_bp.route("/remidio/connections", methods=["GET"])
@roles_required(*REMIDIO_ROLES)
def list_remidio_connections():
    project_id = _optional_int_arg("project_id")
    with transaction_scope() as db:
        return jsonify({"success": True, "data": service.list_connections(db, project_id=project_id)})


@api_bp.route("/remidio/connections", methods=["POST"])
@roles_required(*REMIDIO_ROLES)
def create_remidio_connection():
    payload = _json_payload()
    try:
        with transaction_scope() as db:
            connection = service.create_connection(db, payload)
            return jsonify({"success": True, "data": _connection_response(db, connection.id)}), 201
    except IntegrityError:
        logger.info("Duplicate Remidio connection rejected.")
        return jsonify({"success": False, "error": "Remidio connection conflicts with an existing record."}), 409
    except RemidioIntegrationError as exc:
        return _error_response(exc)


@api_bp.route("/remidio/connections/<int:connection_id>", methods=["PATCH", "POST"])
@roles_required(*REMIDIO_ROLES)
def patch_remidio_connection(connection_id: int):
    payload = _json_payload()
    try:
        with transaction_scope() as db:
            connection = service.patch_connection(db, connection_id, payload)
            return jsonify({"success": True, "data": _connection_response(db, connection.id)})
    except IntegrityError:
        return jsonify({"success": False, "error": "Remidio connection conflicts with an existing record."}), 409
    except RemidioIntegrationError as exc:
        return _error_response(exc)


@api_bp.route("/remidio/connections/<int:connection_id>/refresh-token", methods=["POST"])
@roles_required(*REMIDIO_ROLES)
def refresh_remidio_token(connection_id: int):
    try:
        with transaction_scope() as db:
            return jsonify({"success": True, "data": service.refresh_token(db, connection_id)})
    except RemidioIntegrationError as exc:
        return _error_response(exc)


@api_bp.route("/remidio/connections/<int:connection_id>/sync-sites", methods=["POST"])
@roles_required(*REMIDIO_ROLES)
def sync_remidio_sites(connection_id: int):
    try:
        with transaction_scope() as db:
            return jsonify({"success": True, "data": service.sync_sites(db, connection_id)})
    except RemidioIntegrationError as exc:
        return _error_response(exc)


@api_bp.route("/remidio/connections/<int:connection_id>/sites", methods=["GET"])
@roles_required(*REMIDIO_ROLES)
def list_remidio_sites(connection_id: int):
    try:
        with transaction_scope() as db:
            return jsonify({"success": True, "data": service.list_sites(db, connection_id)})
    except RemidioIntegrationError as exc:
        return _error_response(exc)


@api_bp.route("/remidio/sites/<int:site_id>", methods=["PATCH", "POST"])
@roles_required(*REMIDIO_ROLES)
def patch_remidio_site(site_id: int):
    payload = _json_payload()
    try:
        with transaction_scope() as db:
            site = service.patch_site(db, site_id, payload)
            return jsonify(
                {
                    "success": True,
                    "data": {
                        "id": site.id,
                        "remidio_connection_id": site.remidio_connection_id,
                        "remidio_site_id": site.remidio_site_id,
                        "site_name": site.site_name,
                        "site_domain": site.site_domain,
                        "site_custom_identifier": site.site_custom_identifier,
                        "active": site.active,
                    },
                }
            )
    except IntegrityError:
        return jsonify({"success": False, "error": "site_custom_identifier conflicts with an existing site."}), 409
    except RemidioIntegrationError as exc:
        return _error_response(exc)


@api_bp.route("/remidio/routing-rules", methods=["GET"])
@roles_required(*REMIDIO_ROLES)
def list_remidio_routing_rules():
    connection_id = _optional_int_arg("connection_id")
    project_id = _optional_int_arg("project_id")
    with transaction_scope() as db:
        return jsonify({"success": True, "data": service.list_routing_rules(db, connection_id=connection_id, project_id=project_id)})


@api_bp.route("/remidio/routing-rules", methods=["POST"])
@roles_required(*REMIDIO_ROLES)
def upsert_remidio_routing_rule():
    payload = _json_payload()
    try:
        with transaction_scope() as db:
            rule = service.upsert_routing_rule(db, payload)
            data = next(item for item in service.list_routing_rules(db) if item["id"] == rule.id)
            return jsonify({"success": True, "data": data}), 201
    except IntegrityError:
        return jsonify({"success": False, "error": "Remidio routing rule conflicts with an existing record."}), 409
    except RemidioIntegrationError as exc:
        return _error_response(exc)


@api_bp.route("/remidio/connections/<int:connection_id>/pull/exams-by-date", methods=["POST"])
@roles_required(*REMIDIO_ROLES)
def pull_remidio_exams_by_date(connection_id: int):
    payload = _json_payload()
    try:
        with transaction_scope() as db:
            return jsonify({"success": True, "data": service.pull_exams_by_date(db, connection_id, payload)})
    except RemidioIntegrationError as exc:
        return _error_response(exc)


@api_bp.route("/remidio/connections/<int:connection_id>/pull/latest-patient-exam", methods=["POST"])
@roles_required(*REMIDIO_ROLES)
def pull_remidio_latest_patient_exam(connection_id: int):
    payload = _json_payload()
    try:
        with transaction_scope() as db:
            return jsonify({"success": True, "data": service.pull_latest_patient_exam(db, connection_id, payload)})
    except RemidioIntegrationError as exc:
        return _error_response(exc)


@api_bp.route("/remidio/connections/<int:connection_id>/ingest/staged-files", methods=["POST"])
@roles_required(*REMIDIO_ROLES)
def ingest_remidio_staged_files(connection_id: int):
    payload = _json_payload()
    try:
        with transaction_scope() as db:
            return jsonify({"success": True, "data": service.ingest_connection_files(db, connection_id, payload)})
    except RemidioIntegrationError as exc:
        return _error_response(exc)


def _json_payload() -> dict:
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        payload = {}
    if not payload and request.form:
        payload = request.form.to_dict(flat=False)
        for key, value in list(payload.items()):
            if len(value) == 1:
                payload[key] = value[0]
    return payload


def _optional_int_arg(name: str) -> int | None:
    value = request.args.get(name)
    if value in {None, ""}:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _connection_response(db, connection_id: int) -> dict:
    return next(item for item in service.list_connections(db) if item["id"] == connection_id)


def _error_response(exc: RemidioIntegrationError):
    logger.info("Remidio API integration error: %s", sanitize_log_value(exc))
    return jsonify({"success": False, "error": str(exc)}), exc.status_code
