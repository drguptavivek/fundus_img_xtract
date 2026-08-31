"""EncounterSet data download APIs."""

from __future__ import annotations

import io
from datetime import datetime, timezone

from flask import current_app, jsonify, request, send_file
from flask_login import current_user, login_required
from auth.decorators import reauth_required

from db_transaction_manager import get_db_session
from encounter_sets.export_service import (
    EncounterSetExportFilters,
    EncounterSetExportValidationError,
    export_encounter_sets_xlsx,
)

from . import api_bp


def _optional_positive_int(name: str) -> int | None:
    if name not in request.args:
        return None
    raw = (request.args.get(name) or "").strip()
    if not raw.isdigit() or int(raw) < 1:
        raise EncounterSetExportValidationError(f"{name} must be a positive integer")
    return int(raw)


@api_bp.route("/encounter-sets/export.xlsx", methods=["GET"])
@login_required
def export_encounter_sets():
    """Download one row per scoped EncounterSet for a project and month."""

    month = (request.args.get("month") or "").strip()
    try:
        project_id = _optional_positive_int("project_id")
        lab_unit_id = _optional_positive_int("lab_unit_id")
        filters = EncounterSetExportFilters(
            project_id=project_id, month=month, lab_unit_id=lab_unit_id
        )
        timezone_name = current_user.timezone or current_app.config.get("DEFAULT_DISPLAY_TIMEZONE") or "UTC"
        with get_db_session() as db:
            content = export_encounter_sets_xlsx(
                db,
                user=current_user,
                filters=filters,
                timezone_name=timezone_name,
                include_identifiers=False,
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


@api_bp.route("/encounter-sets/export-pii.xlsx", methods=["GET"])
@login_required
@reauth_required()
def export_encounter_sets_pii():
    """Download the explicit identifier-bearing EncounterSet workbook."""
    month = (request.args.get("month") or "").strip()
    try:
        project_id = _optional_positive_int("project_id")
        lab_unit_id = _optional_positive_int("lab_unit_id")
        filters = EncounterSetExportFilters(
            project_id=project_id, month=month, lab_unit_id=lab_unit_id
        )
        timezone_name = current_user.timezone or current_app.config.get("DEFAULT_DISPLAY_TIMEZONE") or "UTC"
        with get_db_session() as db:
            content = export_encounter_sets_xlsx(
                db,
                user=current_user,
                filters=filters,
                timezone_name=timezone_name,
                include_identifiers=True,
            )
    except EncounterSetExportValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    response = send_file(
        io.BytesIO(content),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"encountersets_pii_{project_id or 'classical'}_{month}_{timestamp}.xlsx",
    )
    response.headers["Cache-Control"] = "no-store"
    return response
