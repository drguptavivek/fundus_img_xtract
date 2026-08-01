"""EncounterSet data download APIs."""

from __future__ import annotations

import io
from datetime import datetime, timezone

from flask import current_app, jsonify, request, send_file
from flask_login import current_user

from auth.roles import roles_required
from db_transaction_manager import get_db_session
from encounter_sets.access import ENCOUNTER_SET_PII_ROLES
from encounter_sets.export_service import (
    EncounterSetExportFilters,
    EncounterSetExportValidationError,
    export_encounter_sets_xlsx,
)

from . import api_bp


@api_bp.route("/encounter-sets/export.xlsx", methods=["GET"])
@roles_required(*ENCOUNTER_SET_PII_ROLES)
def export_encounter_sets():
    """Download one row per scoped EncounterSet for a project and month."""

    project_id = request.args.get("project_id", type=int)
    month = (request.args.get("month") or "").strip()
    if project_id is None:
        return jsonify({"error": "project_id is required and must be an integer"}), 400
    try:
        filters = EncounterSetExportFilters(project_id=project_id, month=month)
        timezone_name = current_user.timezone or current_app.config.get("DEFAULT_DISPLAY_TIMEZONE") or "UTC"
        with get_db_session() as db:
            content = export_encounter_sets_xlsx(
                db,
                user=current_user,
                filters=filters,
                timezone_name=timezone_name,
            )
    except EncounterSetExportValidationError as exc:
        return jsonify({"error": str(exc)}), 400

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    response = send_file(
        io.BytesIO(content),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"encountersets_project_{project_id}_{month}_{timestamp}.xlsx",
    )
    response.headers["Cache-Control"] = "no-store"
    return response
