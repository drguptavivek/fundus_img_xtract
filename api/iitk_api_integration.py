"""JSON API for IITK project configuration, source browsing, and synchronization."""
from __future__ import annotations

import logging

from flask import jsonify, request
from flask_login import current_user
from sqlalchemy.exc import IntegrityError

from auth.roles import roles_required
from db_transaction_manager import transaction_scope
from iitk_api_integration import service
from iitk_api_integration.errors import IITKIntegrationError

from . import api_bp


LOGGER = logging.getLogger("api.iitk_api_integration")
IITK_ROLES = ("admin", "local_admin", "data_manager")


@api_bp.route("/iitk/configurations", methods=["GET"])
@roles_required(*IITK_ROLES)
def list_iitk_configurations():
    with transaction_scope() as db:
        return jsonify({"success": True, "data": service.list_configs(db, manager_user_id=current_user.id)})


@api_bp.route("/iitk/configurations", methods=["POST"])
@roles_required(*IITK_ROLES)
def save_iitk_configuration():
    try:
        with transaction_scope() as db:
            row = service.save_config(db, _payload(), manager_user_id=current_user.id)
            db.flush()
            return jsonify({"success": True, "message": "IITK project configuration saved.",
                "data": service.get_config_payload(db, row.id, manager_user_id=current_user.id)}), 201
    except IntegrityError:
        return jsonify({"success": False, "error": "An IITK configuration already exists for this project."}), 409
    except IITKIntegrationError as exc:
        return _error(exc)


@api_bp.route("/iitk/configurations/<int:config_id>", methods=["PATCH", "POST"])
@roles_required(*IITK_ROLES)
def patch_iitk_configuration(config_id: int):
    payload = _payload()
    payload["id"] = config_id
    try:
        with transaction_scope() as db:
            row = service.save_config(db, payload, manager_user_id=current_user.id)
            return jsonify({"success": True, "message": "IITK project configuration updated.",
                "data": service.get_config_payload(db, row.id, manager_user_id=current_user.id)})
    except IntegrityError:
        return jsonify({"success": False, "error": "The IITK project configuration conflicts with another record."}), 409
    except IITKIntegrationError as exc:
        return _error(exc)


@api_bp.route("/iitk/configurations/<int:config_id>/sessions", methods=["GET"])
@roles_required(*IITK_ROLES)
def browse_iitk_sessions(config_id: int):
    try:
        data = service.browse_sessions(config_id, manager_user_id=current_user.id, filters=request.args.to_dict())
        return jsonify({"success": True, "data": data})
    except IITKIntegrationError as exc:
        return _error(exc)


@api_bp.route("/iitk/configurations/<int:config_id>/sync", methods=["POST"])
@roles_required(*IITK_ROLES)
def queue_iitk_sync(config_id: int):
    from celery_tasks.tasks.iitk_tasks import run_iitk_config_sync_task

    try:
        with transaction_scope() as db:
            service.get_config_payload(db, config_id, manager_user_id=current_user.id)
        full = str(_payload().get("full") or "").lower() in {"1", "true", "yes", "on"}
        task = run_iitk_config_sync_task.delay(config_id, full)
        return jsonify({"success": True, "message": "IITK synchronization queued.",
            "data": {"config_id": config_id, "task_id": task.id, "full": full}}), 202
    except IITKIntegrationError as exc:
        return _error(exc)


def _payload() -> dict:
    if request.is_json:
        return dict(request.get_json(silent=True) or {})
    return request.form.to_dict()


def _error(exc: IITKIntegrationError):
    LOGGER.info("IITK API request rejected: %s", type(exc).__name__)
    return jsonify({"success": False, "error": str(exc)}), 400
