"""Download APIs for analytics export surfaces."""

from __future__ import annotations

import io
from datetime import datetime, timezone

from flask import request, send_file
from flask_login import current_user
from flask_login import login_required
from werkzeug.exceptions import BadRequest

from analytics.encounter_exports import (
    EncounterExportFilters,
    export_encounter_task_results_xlsx,
)
from auth.decorators import reauth_required
from db_transaction_manager import get_db_session
from utils.date_utils import parse_date_yyyy_mm_dd

from . import api_bp


def _filters_from_request() -> EncounterExportFilters:
    capture_date = None
    start_date = None
    end_date = None
    capture_date_str = (request.args.get("capture_date") or "").strip()
    start_date_str = (request.args.get("start_date") or "").strip()
    end_date_str = (request.args.get("end_date") or "").strip()
    if capture_date_str:
        capture_date = parse_date_yyyy_mm_dd(capture_date_str)
    if start_date_str:
        start_date = parse_date_yyyy_mm_dd(start_date_str)
    if end_date_str:
        end_date = parse_date_yyyy_mm_dd(end_date_str)
    def optional_positive_int(name: str) -> int | None:
        if name not in request.args:
            return None
        value = (request.args.get(name) or "").strip()
        if not value.isdigit() or int(value) < 1:
            raise BadRequest(f"{name} must be a positive integer")
        return int(value)

    project_values = request.args.getlist("project_id")
    if any(not value.strip().isdigit() or int(value) < 1 for value in project_values):
        raise BadRequest("each project_id must be a positive integer")
    project_ids = tuple(int(value) for value in project_values)
    include_classical = None
    if "include_classical" in request.args:
        value = (request.args.get("include_classical") or "").strip()
        if value not in {"0", "1"}:
            raise BadRequest("include_classical must be 0 or 1")
        include_classical = value == "1"
    return EncounterExportFilters(
        hospital_id=optional_positive_int("hospital_id"),
        lab_unit_id=optional_positive_int("lab_unit_id"),
        capture_date=capture_date,
        start_date=start_date,
        end_date=end_date,
        project_ids=project_ids,
        include_classical=include_classical,
    )


def _xlsx_response(content: bytes, stem: str):
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return send_file(
        io.BytesIO(content),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"{stem}_{timestamp}.xlsx",
    )


@api_bp.route("/analytics/encounters/export/task-results.xlsx", methods=["GET"])
@login_required
def export_encounter_task_results():
    """Download image/task-wise results with identifiers masked."""

    with get_db_session() as db:
        content = export_encounter_task_results_xlsx(
            db, current_user, _filters_from_request(), include_identifiers=False
        )
    return _xlsx_response(content, "encounter_task_results")


@api_bp.route("/analytics/encounters/export/task-results-pii.xlsx", methods=["GET"])
@login_required
@reauth_required()
def export_encounter_task_results_pii():
    """Download the explicit identifier-bearing project export."""
    with get_db_session() as db:
        content = export_encounter_task_results_xlsx(
            db, current_user, _filters_from_request(), include_identifiers=True
        )
    return _xlsx_response(content, "encounter_task_results_pii")
