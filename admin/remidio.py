"""Admin UI for Remidio API connection and site routing management."""
from __future__ import annotations

from typing import Any

from flask import current_app, jsonify, render_template, request
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from auth.roles import roles_required
from db_transaction_manager import transaction_scope
from models import (
    Camera,
    Disease,
    EncounterFile,
    EncounterFilePDF,
    GradingTask,
    LabUnit,
    PatientEncounters,
    Project,
    RemidioConnection,
    RemidioExam,
    RemidioImage,
    RemidioReport,
    RemidioRoutingRule,
    RemidioSite,
)
from utils.log_sanitize import sanitize_log_value
from zip_processor import cleanup_processed_zip_intake_files


@roles_required("admin", "data_manager")
def remidio_admin():
    """Render the Remidio connection administration page."""
    with transaction_scope() as db:
        return render_template("admin/remidio.html", **_context(db))


@roles_required("admin", "data_manager")
def remidio_workspace():
    """Render the HTMX workspace fragment after Remidio mutations."""
    with transaction_scope() as db:
        return render_template("admin/partials/remidio_workspace.html", **_context(db))


@roles_required("admin", "data_manager")
def stuck_remidio_uploads_status():
    """Return a dry-run view of processed Remidio ZIPs still in intake."""
    date_folder = request.args.get("date_folder") or None
    limit = _parse_optional_int(request.args.get("limit"), default=None)
    with transaction_scope() as db:
        result = cleanup_processed_zip_intake_files(
            db,
            date_folder=date_folder,
            dry_run=True,
            limit=limit,
        )
    return jsonify({"success": True, "data": result})


@roles_required("admin", "data_manager")
def cleanup_stuck_remidio_uploads():
    """Run the guarded cleanup for processed Remidio ZIPs still in intake."""
    payload = request.get_json(silent=True) or request.form
    date_folder = payload.get("date_folder") or None
    limit = _parse_optional_int(payload.get("limit"), default=None)
    dry_run = _parse_bool(payload.get("dry_run"), default=False)

    current_app.logger.warning(
        "Admin requested stuck Remidio ZIP cleanup dry_run=%s date_folder=%s limit=%s",
        dry_run,
        sanitize_log_value(date_folder),
        limit,
    )
    with transaction_scope() as db:
        result = cleanup_processed_zip_intake_files(
            db,
            date_folder=date_folder,
            dry_run=dry_run,
            limit=limit,
        )
    status_code = 200 if result["errors"] == 0 else 207
    return jsonify({"success": result["errors"] == 0, "data": result}), status_code


def _parse_optional_int(value, *, default: int | None) -> int | None:
    if value in (None, ""):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(parsed, 0)


def _parse_bool(value, *, default: bool) -> bool:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _context(db) -> dict[str, Any]:
    connections = (
        db.execute(
            select(RemidioConnection)
            .options(
                selectinload(RemidioConnection.sites),
                selectinload(RemidioConnection.routing_rules).selectinload(RemidioRoutingRule.project),
                selectinload(RemidioConnection.routing_rules).selectinload(RemidioRoutingRule.lab_unit),
                selectinload(RemidioConnection.routing_rules).selectinload(RemidioRoutingRule.camera),
                selectinload(RemidioConnection.routing_rules).selectinload(RemidioRoutingRule.default_disease),
            )
            .order_by(RemidioConnection.active.desc(), RemidioConnection.name)
        )
        .scalars()
        .unique()
        .all()
    )
    sites = (
        db.execute(
            select(RemidioSite)
            .options(selectinload(RemidioSite.connection), selectinload(RemidioSite.routing_rules))
            .order_by(RemidioSite.remidio_connection_id, RemidioSite.site_name, RemidioSite.id)
        )
        .scalars()
        .unique()
        .all()
    )
    rules = (
        db.execute(
            select(RemidioRoutingRule)
            .options(
                selectinload(RemidioRoutingRule.connection),
                selectinload(RemidioRoutingRule.site),
                selectinload(RemidioRoutingRule.project),
                selectinload(RemidioRoutingRule.lab_unit),
                selectinload(RemidioRoutingRule.camera),
                selectinload(RemidioRoutingRule.default_disease),
            )
            .order_by(RemidioRoutingRule.active.desc(), RemidioRoutingRule.remidio_connection_id, RemidioRoutingRule.site_custom_identifier)
        )
        .scalars()
        .unique()
        .all()
    )
    return {
        "connections": connections,
        "sites": sites,
        "rules": rules,
        "projects": db.execute(select(Project).order_by(Project.active.desc(), Project.title)).scalars().all(),
        "lab_units": db.execute(select(LabUnit).options(selectinload(LabUnit.hospital)).order_by(LabUnit.name)).scalars().all(),
        "cameras": db.execute(select(Camera).order_by(Camera.name)).scalars().all(),
        "diseases": db.execute(select(Disease).order_by(Disease.name)).scalars().all(),
        "connection_stats": _connection_stats(db),
        "site_stats": _site_stats(db),
    }


def _connection_stats(db) -> dict[int, dict[str, int]]:
    stats: dict[int, dict[str, int]] = {}
    for connection_id, count in db.execute(select(RemidioExam.remidio_connection_id, func.count(RemidioExam.id)).group_by(RemidioExam.remidio_connection_id)):
        stats.setdefault(connection_id, {})["exams"] = count
    for connection_id, count in db.execute(
        select(RemidioExam.remidio_connection_id, func.count(RemidioExam.patient_encounter_id)).where(RemidioExam.patient_encounter_id.is_not(None)).group_by(RemidioExam.remidio_connection_id)
    ):
        stats.setdefault(connection_id, {})["encounters"] = count
    return stats


def _site_stats(db) -> dict[int, dict[str, int]]:
    stats: dict[int, dict[str, int]] = {}
    rows = (
        db.execute(
            select(
                RemidioExam.remidio_site_id,
                func.count(func.distinct(RemidioExam.id)),
                func.count(func.distinct(PatientEncounters.id)),
                func.count(func.distinct(EncounterFile.id)),
                func.count(func.distinct(EncounterFilePDF.id)),
                func.count(func.distinct(GradingTask.id)),
            )
            .outerjoin(PatientEncounters, PatientEncounters.id == RemidioExam.patient_encounter_id)
            .outerjoin(RemidioImage, RemidioImage.remidio_exam_id == RemidioExam.id)
            .outerjoin(EncounterFile, EncounterFile.id == RemidioImage.encounter_file_id)
            .outerjoin(RemidioReport, RemidioReport.remidio_exam_id == RemidioExam.id)
            .outerjoin(EncounterFilePDF, EncounterFilePDF.id == RemidioReport.encounter_file_pdf_id)
            .outerjoin(GradingTask, GradingTask.encounter_file_id == EncounterFile.id)
            .where(RemidioExam.remidio_site_id.is_not(None))
            .group_by(RemidioExam.remidio_site_id)
        )
        .all()
    )
    for site_id, exams, encounters, images, pdfs, tasks in rows:
        stats[site_id] = {
            "exams": exams,
            "encounters": encounters,
            "images": images,
            "pdfs": pdfs,
            "tasks": tasks,
        }
    return stats
