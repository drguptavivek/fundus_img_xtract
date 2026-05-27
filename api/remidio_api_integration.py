"""API routes for Remidio gateway configuration and metadata pulls."""

from __future__ import annotations

import logging

from flask import jsonify, request
from flask_login import current_user
from sqlalchemy.exc import IntegrityError

from auth.roles import roles_required
from db_transaction_manager import transaction_scope
from remidio_api_integration import routing as api_routing
from remidio_api_integration import service
from remidio_api_integration.errors import RemidioConfigError, RemidioIntegrationError
from utils.log_sanitize import sanitize_log_value

from . import api_bp


logger = logging.getLogger("api.remidio_api_integration")
REMIDIO_ROLES = ("admin", "data_manager")
REMIDIO_BINDING_ROLES = ("admin", "local_admin", "data_manager")


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


@api_bp.route("/remidio/api-source-rules", methods=["GET"])
@roles_required(*REMIDIO_ROLES)
def list_remidio_api_source_rules():
    connection_id = _optional_int_arg("connection_id")
    with transaction_scope() as db:
        return jsonify({"success": True, "data": api_routing.list_api_source_rules(db, connection_id=connection_id)})


@api_bp.route("/remidio/api-source-rules", methods=["POST"])
@roles_required(*REMIDIO_ROLES)
def upsert_remidio_api_source_rule():
    payload = _json_payload()
    try:
        with transaction_scope() as db:
            rule = api_routing.upsert_api_source_rule(db, payload)
            data = next(item for item in api_routing.list_api_source_rules(db) if item["id"] == rule.id)
            return jsonify({"success": True, "data": data}), 201
    except IntegrityError:
        return jsonify({"success": False, "error": "Remidio API source rule conflicts with an existing active rule."}), 409
    except RemidioIntegrationError as exc:
        return _error_response(exc)


@api_bp.route("/remidio/api-bindings", methods=["GET"])
@roles_required(*REMIDIO_BINDING_ROLES)
def list_remidio_api_bindings():
    project_upload_profile_id = _optional_int_arg("project_upload_profile_id")
    source_rule_id = _optional_int_arg("source_rule_id")
    with transaction_scope() as db:
        return jsonify(
            {
                "success": True,
                "data": api_routing.list_api_bindings(
                    db,
                    project_upload_profile_id=project_upload_profile_id,
                    source_rule_id=source_rule_id,
                ),
            }
        )


@api_bp.route("/remidio/api-bindings", methods=["POST"])
@roles_required(*REMIDIO_BINDING_ROLES)
def upsert_remidio_api_binding():
    payload = _json_payload()
    try:
        with transaction_scope() as db:
            binding = api_routing.upsert_api_binding(db, payload, manager_user_id=current_user.id)
            data = next(item for item in api_routing.list_api_bindings(db) if item["id"] == binding.id)
            return jsonify({"success": True, "data": data}), 201
    except IntegrityError:
        return jsonify({"success": False, "error": "Remidio API binding conflicts with an existing active date window."}), 409
    except RemidioIntegrationError as exc:
        return _error_response(exc)


@api_bp.route("/remidio/api-routing-profiles", methods=["GET"])
@roles_required(*REMIDIO_BINDING_ROLES)
def list_remidio_api_routing_profiles():
    project_id = _optional_int_arg("project_id")
    with transaction_scope() as db:
        return jsonify({"success": True, "data": api_routing.list_routing_profiles(db, project_id=project_id)})


@api_bp.route("/remidio/api-routing-profiles", methods=["POST"])
@roles_required(*REMIDIO_BINDING_ROLES)
def upsert_remidio_api_routing_profile():
    payload = _json_payload()
    try:
        with transaction_scope() as db:
            profile = api_routing.upsert_routing_profile(db, payload)
            data = next(item for item in api_routing.list_routing_profiles(db) if item["id"] == profile.id)
            return jsonify({"success": True, "data": data, "message": "Remidio API routing profile saved."}), 201
    except IntegrityError:
        return jsonify({"success": False, "error": "Remidio API routing profile conflicts with an existing profile."}), 409
    except RemidioIntegrationError as exc:
        return _error_response(exc)


@api_bp.route("/remidio/api-routing-profiles/<int:routing_profile_id>", methods=["DELETE"])
@roles_required(*REMIDIO_BINDING_ROLES)
def delete_remidio_api_routing_profile(routing_profile_id: int):
    try:
        with transaction_scope() as db:
            api_routing.delete_routing_profile(db, routing_profile_id)
            return jsonify({"success": True, "message": "Remidio API routing profile deleted."})
    except RemidioIntegrationError as exc:
        return _error_response(exc)


@api_bp.route("/remidio/api-routing-profile-routes", methods=["POST"])
@roles_required(*REMIDIO_BINDING_ROLES)
def create_remidio_api_routing_profile_with_route():
    payload = _json_payload()
    try:
        with transaction_scope() as db:
            profile, binding = api_routing.create_routing_profile_with_route(db, payload, manager_user_id=current_user.id)
            data = {
                "routing_profile": next(item for item in api_routing.list_routing_profiles(db) if item["id"] == profile.id),
                "route": next(item for item in api_routing.list_api_bindings(db) if item["id"] == binding.id),
            }
            return jsonify({"success": True, "data": data, "message": "Remidio API routing profile created."}), 201
    except IntegrityError:
        return jsonify({"success": False, "error": "Remidio API routing profile or route conflicts with an existing record."}), 409
    except RemidioIntegrationError as exc:
        return _error_response(exc)


@api_bp.route("/remidio/api-routing-rules", methods=["GET"])
@roles_required(*REMIDIO_BINDING_ROLES)
def list_remidio_api_routing_rules():
    project_id = _optional_int_arg("project_id")
    with transaction_scope() as db:
        profiles = api_routing.list_routing_profiles(db, project_id=project_id)
        routes = [route for profile in profiles for route in profile["routes"]]
        return jsonify({"success": True, "data": routes})


@api_bp.route("/remidio/api-routing-rules", methods=["POST"])
@roles_required(*REMIDIO_BINDING_ROLES)
def upsert_remidio_api_routing_rule():
    payload = _json_payload()
    try:
        with transaction_scope() as db:
            binding = api_routing.upsert_routing_profile_route(db, payload, manager_user_id=current_user.id)
            data = next(item for item in api_routing.list_api_bindings(db) if item["id"] == binding.id)
            return jsonify({"success": True, "data": data, "message": "Remidio API routing rule saved."}), 201
    except IntegrityError:
        return jsonify({"success": False, "error": "Remidio API routing rule conflicts with an existing active date window."}), 409
    except RemidioIntegrationError as exc:
        return _error_response(exc)


@api_bp.route("/remidio/api-routing-profiles/<int:routing_profile_id>/sync", methods=["POST"])
@roles_required(*REMIDIO_BINDING_ROLES)
def sync_remidio_api_routing_profile(routing_profile_id: int):
    payload = _json_payload()
    try:
        with transaction_scope() as db:
            data = service.create_routing_profile_sync_job(
                db,
                routing_profile_id=routing_profile_id,
                payload=payload,
                requested_by_user_id=current_user.id,
                requested_by_username=current_user.username,
            )
        service.enqueue_routing_profile_sync_job(data["job_id"], user_id=current_user.id)
        return jsonify({"success": True, "data": data, "message": "Remidio API sync job queued."}), 202
    except RemidioIntegrationError as exc:
        return _error_response(exc)


@api_bp.route("/remidio/projects/<int:project_id>/sync", methods=["POST"])
@roles_required(*REMIDIO_BINDING_ROLES, "fileUploader")
def sync_remidio_api_project(project_id: int):
    payload = _json_payload()
    return _sync_remidio_api_project_from_payload(project_id, payload)


@api_bp.route("/remidio/projects/sync", methods=["POST"])
@roles_required(*REMIDIO_BINDING_ROLES, "fileUploader")
def sync_selected_remidio_api_project():
    payload = _json_payload()
    try:
        project_id = _required_int_payload(payload, "project_id")
    except RemidioIntegrationError as exc:
        return _error_response(exc)
    return _sync_remidio_api_project_from_payload(project_id, payload)


def _sync_remidio_api_project_from_payload(project_id: int, payload: dict):
    try:
        with transaction_scope() as db:
            data = service.create_project_sync_job(
                db,
                project_id=project_id,
                payload=payload,
                requested_by_user_id=current_user.id,
                requested_by_username=current_user.username,
            )
        if data["items_created"] > 0:
            service.enqueue_project_sync_job(data["job_id"], user_id=current_user.id)
        return jsonify({"success": True, "data": data, "message": "Remidio API project sync queued."}), 202
    except RemidioIntegrationError as exc:
        return _error_response(exc)


@api_bp.route("/remidio/project-sync-jobs/<int:job_id>/pause", methods=["POST"])
@roles_required(*REMIDIO_BINDING_ROLES, "fileUploader")
def pause_remidio_api_project_sync_job(job_id: int):
    try:
        with transaction_scope() as db:
            data = service.pause_project_sync_job(db, job_id)
        return jsonify({"success": True, "data": data, "message": "Remidio API project sync paused."})
    except RemidioIntegrationError as exc:
        return _error_response(exc)


@api_bp.route("/remidio/project-sync-jobs/<int:job_id>/resume", methods=["POST"])
@roles_required(*REMIDIO_BINDING_ROLES, "fileUploader")
def resume_remidio_api_project_sync_job(job_id: int):
    try:
        with transaction_scope() as db:
            data = service.resume_project_sync_job(db, job_id)
        service.enqueue_project_sync_job(job_id, user_id=current_user.id)
        return jsonify({"success": True, "data": data, "message": "Remidio API project sync resumed."})
    except RemidioIntegrationError as exc:
        return _error_response(exc)


@api_bp.route("/remidio/project-sync-jobs/<int:job_id>/cancel", methods=["POST"])
@roles_required(*REMIDIO_BINDING_ROLES, "fileUploader")
def cancel_remidio_api_project_sync_job(job_id: int):
    try:
        with transaction_scope() as db:
            data = service.cancel_project_sync_job(db, job_id)
        return jsonify({"success": True, "data": data, "message": "Remidio API project sync cancelled."})
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


def _required_int_payload(payload: dict, name: str) -> int:
    value = payload.get(name)
    if value in {None, ""}:
        raise RemidioConfigError(f"{name} is required.")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise RemidioConfigError(f"{name} must be an integer.") from exc


def _connection_response(db, connection_id: int) -> dict:
    return next(item for item in service.list_connections(db) if item["id"] == connection_id)


def _error_response(exc: RemidioIntegrationError):
    logger.info("Remidio API integration error: %s", sanitize_log_value(exc))
    return jsonify({"success": False, "error": str(exc)}), exc.status_code
