"""REST API for System Admin project configuration."""
from dataclasses import asdict

from flask import jsonify, request
from flask_login import current_user

from auth.roles import roles_required
from db_transaction_manager import transaction_scope
from project_configuration.service import (
    ProjectLabConfigurationError,
    list_project_lab_units,
    replace_project_lab_units,
)

from . import api_bp


@api_bp.route("/projects/<int:project_id>/lab-units", methods=["GET"])
@roles_required("admin")
def get_project_lab_units(project_id: int):
    with transaction_scope() as db:
        rows = list_project_lab_units(db, project_id=project_id)
    return jsonify({"success": True, "lab_units": [asdict(row) for row in rows]})


@api_bp.route("/projects/<int:project_id>/lab-units", methods=["PUT", "POST"])
@roles_required("admin")
def put_project_lab_units(project_id: int):
    payload = request.get_json(silent=True) if request.is_json else request.form
    values = payload.get("lab_unit_ids", []) if request.is_json else request.form.getlist("lab_unit_ids")
    if not isinstance(values, list):
        return jsonify({"success": False, "error": "lab_unit_ids must be a list."}), 400
    try:
        lab_unit_ids = [int(value) for value in values]
        raw_settings = payload.get("site_settings", {}) if request.is_json else {}
        if not isinstance(raw_settings, dict):
            raise ProjectLabConfigurationError("site_settings must be an object keyed by Lab Unit ID.")
        site_settings = {
            int(lab_unit_id): settings
            for lab_unit_id, settings in raw_settings.items()
            if isinstance(settings, dict)
        }
        if len(site_settings) != len(raw_settings):
            raise ProjectLabConfigurationError("Each site_settings value must be an object.")
        with transaction_scope() as db:
            rows = replace_project_lab_units(
                db,
                actor=current_user,
                project_id=project_id,
                lab_unit_ids=lab_unit_ids,
                site_settings=site_settings,
            )
    except (TypeError, ValueError, ProjectLabConfigurationError) as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    return jsonify({"success": True, "lab_units": [asdict(row) for row in rows]})
