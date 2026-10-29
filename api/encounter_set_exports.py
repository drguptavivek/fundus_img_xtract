"""EncounterSet data download APIs."""

from __future__ import annotations

import io
from datetime import datetime, timezone

from flask import current_app, jsonify, request, send_file
from flask_login import current_user, login_required
from auth.decorators import reauth_required
from authz.exceptions import AuthorizationDenied

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


def _export_denied(exc: AuthorizationDenied, *, pii: bool):
    if exc.reason == "classical_pii_export_requires_admin":
        message = "Identifier-bearing exports without a project require an administrator."
    elif exc.reason == "export_lab_unit_unauthorized":
        message = "You do not have export access to the selected lab unit. Ask an administrator to review your access."
    else:
        roles = "pii_exporter" if pii else "data_exporter or pii_exporter"
        message = (
            f"You need the {roles} role for this project and lab scope, or administrator access. "
            "Ask an administrator to review your access. If your export role is limited to a lab unit, "
            "include its lab_unit_id in the request."
        )
    return jsonify({"error": message}), 403


@api_bp.route("/encounter-sets/export.xlsx", methods=["GET"])
@login_required
def export_encounter_sets():
    """Download one row per scoped EncounterSet for a project and month.

    Omit ``month`` to export every month for the project.
    """

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
    except AuthorizationDenied as exc:
        return _export_denied(exc, pii=False)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    response = send_file(
        io.BytesIO(content),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"encountersets_project_{project_id}_{month or 'all-months'}_{timestamp}.xlsx",
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@api_bp.route("/encounter-sets/export-pii.xlsx", methods=["GET"])
@login_required
@reauth_required()
def export_encounter_sets_pii():
    """Download the explicit identifier-bearing EncounterSet workbook.

    Omit ``month`` to export every month for the project.
    """
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
    except AuthorizationDenied as exc:
        return _export_denied(exc, pii=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    response = send_file(
        io.BytesIO(content),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"encountersets_pii_{project_id or 'classical'}_{month or 'all-months'}_{timestamp}.xlsx",
    )
    response.headers["Cache-Control"] = "no-store"
    return response
