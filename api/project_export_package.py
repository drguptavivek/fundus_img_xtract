"""Admin-role API for DuckDB export packages. See docs/API/project_export/README.md.

Routes only authenticate, parse the query into an ``ExportRequest``, call the
``project_export`` service and stream the file; all rules live in the module.
"""
from __future__ import annotations

import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from flask import jsonify, request, send_file

from auth.decorators import reauth_required
from auth.roles import roles_required
from db_transaction_manager import get_db_session
from project_export import ExportRequest, ProjectExportError, export_options, export_package, export_workbook
from utils.log_sanitize import sanitize_log_value
from utils.rate_limiter import rate_limit
from utils.sensitive_operations import log_export_completed, log_export_failed, log_export_initiated

from . import api_bp

OPERATION = "project_duckdb_export"
XLSX_MIMETYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _error(status: int, code: str, message: str):
    return jsonify({"error": code, "message": message}), status


def _stream(export_request: ExportRequest, *, workbook: bool = False):
    log_export_initiated(OPERATION, {**export_request.audit_details(), "format": "xlsx" if workbook else "duckdb"})
    workdir = Path(tempfile.mkdtemp(prefix="project_export_"))
    try:
        with get_db_session() as db:
            result = (export_workbook if workbook else export_package)(db, export_request, workdir)
    except ProjectExportError as exc:
        shutil.rmtree(workdir, ignore_errors=True)
        log_export_failed(OPERATION, str(sanitize_log_value(exc)))
        return _error(exc.status, exc.code, str(exc))
    except ImportError:
        shutil.rmtree(workdir, ignore_errors=True)
        log_export_failed(OPERATION, "duckdb is not installed")
        return _error(503, "unavailable", "The export engine is not installed on this server.")
    except Exception as exc:
        shutil.rmtree(workdir, ignore_errors=True)
        log_export_failed(OPERATION, str(sanitize_log_value(exc)))
        raise
    log_export_completed(OPERATION, str(result.path), result.total_rows)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    suffix = "_identifiers" if export_request.include_identifiers else ""
    response = send_file(
        result.path, mimetype=XLSX_MIMETYPE if workbook else "application/octet-stream", as_attachment=True,
        download_name=f"{result.path.stem}{suffix}_{stamp}{result.path.suffix}",
    )
    response.headers["Cache-Control"] = "no-store"
    response.call_on_close(lambda: shutil.rmtree(workdir, ignore_errors=True))
    return response


@api_bp.route("/admin/project-export/options", methods=["GET"])
@roles_required("admin")
def project_export_options():
    """Projects, hospitals and lab units the export form can choose from."""
    with get_db_session() as db:
        return jsonify(export_options(db))


@api_bp.route("/admin/projects/<int:project_id>/export.duckdb", methods=["GET"])
@roles_required("admin")
@reauth_required()
@rate_limit("6 per hour")
def download_project_duckdb(project_id: int):
    """DuckDB package for one project. ``?identifiers=1`` includes patient identifiers (default: withheld)."""
    return _stream(ExportRequest.from_query(request.args, project_id=project_id))


@api_bp.route("/admin/no-project/export.duckdb", methods=["GET"])
@roles_required("admin")
@reauth_required()
@rate_limit("6 per hour")
def download_no_project_duckdb():
    """DuckDB package for encounters in no project; repeat ``hospital_id`` / ``lab_unit_id`` to select several."""
    try:
        export_request = ExportRequest.from_query(request.args)
    except ProjectExportError as exc:
        return _error(exc.status, exc.code, str(exc))
    return _stream(export_request)


@api_bp.route("/admin/projects/<int:project_id>/export.xlsx", methods=["GET"])
@roles_required("admin")
@reauth_required()
@rate_limit("6 per hour")
def download_project_workbook(project_id: int):
    """Excel workbook generated from the same package (long cells truncated, notes on the xlsx_notes sheet)."""
    return _stream(ExportRequest.from_query(request.args, project_id=project_id), workbook=True)


@api_bp.route("/admin/no-project/export.xlsx", methods=["GET"])
@roles_required("admin")
@reauth_required()
@rate_limit("6 per hour")
def download_no_project_workbook():
    """Excel workbook for encounters in no project; same selection parameters as the DuckDB endpoint."""
    try:
        export_request = ExportRequest.from_query(request.args)
    except ProjectExportError as exc:
        return _error(exc.status, exc.code, str(exc))
    return _stream(export_request, workbook=True)
