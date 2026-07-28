"""Download APIs for analytics export surfaces."""

from __future__ import annotations

import io
from datetime import datetime, timezone

from flask import request, send_file
from flask_login import current_user

from analytics.encounter_exports import (
    EncounterExportFilters,
    export_encounter_task_results_xlsx,
)
from auth.roles import roles_required
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
    project_ids = tuple(
        int(value)
        for value in request.args.getlist("project_id")
        if value.isdigit()
    )
    include_classical = (
        request.args.get("include_classical") == "1"
        if "include_classical" in request.args
        else None
    )
    return EncounterExportFilters(
        hospital_id=request.args.get("hospital_id", type=int),
        lab_unit_id=request.args.get("lab_unit_id", type=int),
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
@roles_required("admin", "local_admin", "data_manager")
def export_encounter_task_results():
    """Download image/task-wise encounter results and full OCR identifiers as XLSX."""

    with get_db_session() as db:
        content = export_encounter_task_results_xlsx(db, current_user, _filters_from_request())
    return _xlsx_response(content, "encounter_task_results")
