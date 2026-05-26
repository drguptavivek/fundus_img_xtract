"""Admin UI for Remidio API connection and site routing management."""
from __future__ import annotations

from typing import Any

from flask import current_app, jsonify, render_template, request
from sqlalchemy import func, or_, select
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
    RemidioSite,
)
from remidio_api_integration.models import ProjectUploadProfileRemidioApiBinding, RemidioApiSourceRule
from remidio_api_integration.models import RemidioApiRoutingProfile
from upload_profiles.models import ProjectUploadProfile
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


@roles_required("admin", "data_manager", "local_admin")
def remidio_api_routing_dashboard():
    """Render the Remidio API routing dashboard."""
    with transaction_scope() as db:
        return render_template("admin/remidio_api_routing.html", **_routing_context(db))


@roles_required("admin", "data_manager", "local_admin")
def remidio_api_routing_workspace():
    """Render the Remidio API routing dashboard workspace fragment."""
    with transaction_scope() as db:
        return render_template("admin/partials/remidio_api_routing_workspace.html", **_routing_context(db))


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
            select(RemidioApiSourceRule)
            .options(
                selectinload(RemidioApiSourceRule.connection),
                selectinload(RemidioApiSourceRule.site),
                selectinload(RemidioApiSourceRule.bindings)
                .selectinload(ProjectUploadProfileRemidioApiBinding.project_profile)
                .selectinload(ProjectUploadProfile.project),
                selectinload(RemidioApiSourceRule.bindings)
                .selectinload(ProjectUploadProfileRemidioApiBinding.project_profile)
                .selectinload(ProjectUploadProfile.profile),
                selectinload(RemidioApiSourceRule.bindings).selectinload(ProjectUploadProfileRemidioApiBinding.lab_unit),
                selectinload(RemidioApiSourceRule.bindings).selectinload(ProjectUploadProfileRemidioApiBinding.camera),
            )
            .order_by(RemidioApiSourceRule.active.desc(), RemidioApiSourceRule.remidio_connection_id, RemidioApiSourceRule.site_custom_identifier)
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


def _routing_context(db) -> dict[str, Any]:
    routing_profiles = (
        db.execute(
            select(RemidioApiRoutingProfile)
            .options(
                selectinload(RemidioApiRoutingProfile.project),
                selectinload(RemidioApiRoutingProfile.routes)
                .selectinload(ProjectUploadProfileRemidioApiBinding.source_rule)
                .selectinload(RemidioApiSourceRule.connection),
                selectinload(RemidioApiRoutingProfile.routes)
                .selectinload(ProjectUploadProfileRemidioApiBinding.source_rule)
                .selectinload(RemidioApiSourceRule.site),
                selectinload(RemidioApiRoutingProfile.routes)
                .selectinload(ProjectUploadProfileRemidioApiBinding.project_profile)
                .selectinload(ProjectUploadProfile.profile),
                selectinload(RemidioApiRoutingProfile.routes).selectinload(ProjectUploadProfileRemidioApiBinding.lab_unit),
                selectinload(RemidioApiRoutingProfile.routes).selectinload(ProjectUploadProfileRemidioApiBinding.camera),
            )
            .order_by(RemidioApiRoutingProfile.active.desc(), RemidioApiRoutingProfile.name)
        )
        .scalars()
        .unique()
        .all()
    )
    project_profiles = (
        db.execute(
            select(ProjectUploadProfile)
            .options(
                selectinload(ProjectUploadProfile.project),
                selectinload(ProjectUploadProfile.profile),
            )
            .join(ProjectUploadProfile.profile)
            .where(ProjectUploadProfile.active.is_(True))
            .order_by(ProjectUploadProfile.project_id, ProjectUploadProfile.upload_profile_id)
        )
        .scalars()
        .unique()
        .all()
    )
    automated_project_profiles = [
        mapping
        for mapping in project_profiles
        if mapping.profile and mapping.profile.active and mapping.profile.automated_remidio_populated
    ]
    return {
        "routing_profiles": routing_profiles,
        "projects": db.execute(select(Project).where(Project.active.is_(True)).order_by(Project.title)).scalars().all(),
        "connections": (
            db.execute(select(RemidioConnection).where(RemidioConnection.active.is_(True)).order_by(RemidioConnection.name))
            .scalars()
            .all()
        ),
        "sites": (
            db.execute(
                select(RemidioSite)
                .options(selectinload(RemidioSite.connection))
                .where(RemidioSite.active.is_(True))
                .order_by(RemidioSite.remidio_connection_id, RemidioSite.site_name, RemidioSite.id)
            )
            .scalars()
            .unique()
            .all()
        ),
        "automated_project_profiles": automated_project_profiles,
        "lab_units": db.execute(select(LabUnit).options(selectinload(LabUnit.hospital)).order_by(LabUnit.name)).scalars().all(),
        "cameras": db.execute(select(Camera).order_by(Camera.name)).scalars().all(),
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
                func.count(func.distinct(RemidioImage.id)).filter(
                    or_(
                        RemidioImage.encounter_file_id.is_not(None),
                        RemidioImage.encounter_set_image_id.is_not(None),
                    )
                ),
                func.count(func.distinct(RemidioReport.id)).filter(
                    or_(
                        RemidioReport.encounter_file_pdf_id.is_not(None),
                        RemidioReport.encounter_set_attachment_id.is_not(None),
                    )
                ),
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
