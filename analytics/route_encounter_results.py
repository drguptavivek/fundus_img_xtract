"""Routes for encounter results."""

from __future__ import annotations

import math
from datetime import datetime, date as _date, time, timezone
from typing import Any

from flask import current_app, render_template, request, url_for, flash, redirect
from flask_login import current_user
from auth.roles import roles_required
import sqlalchemy as sa
from sqlalchemy.orm import selectinload

from app_cache import cache
from . import bp
from models import (
    Area,
    Camera,
    Disease,
    DirectImageUpload,
    DiabeticRetinopathyReport,
    EncounterFile,
    EncounterSetImage,
    GlaucomaResultsCleaned,
    GradingTask,
    Hospital,
    LabUnit,
    PatientEncounters,
    Project,
)
from db_transaction_manager import get_db_session
from analytics.utils import build_encounter_result_payload, fetch_image_task_details
from authz import scope
from utils.date_utils import parse_date_yyyy_mm_dd
from utils.pii_masking import should_mask_pii


def _normalize_datetime(value: datetime | _date | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, _date):
        return datetime.combine(value, time.min, timezone.utc)
    return None


_ENCOUNTER_RESULTS_CACHE_TIMEOUT_SECONDS = 10 * 60


def _filter_query_params(filter_params: dict[str, Any]) -> dict[str, Any]:
    """Build URL query params while preserving repeated multi-select values."""

    params: dict[str, Any] = {}
    for key, value in filter_params.items():
        if isinstance(value, (list, tuple)):
            if value:
                params[key] = list(value)
            continue
        if value:
            params[key] = value
    return params


def _encounter_results_cache_key() -> str:
    return f"analytics:encounters:v2:u{current_user.id}:{request.query_string.decode('utf-8')}"


@bp.route("/encounters", methods=["GET"])
@roles_required(
    "admin",
    "local_admin",
    "fileUploader",
    "ophthalmologist",
    "data_manager",
    "analytics_viewer",
    "optometrist",
)
@cache.cached(
    timeout=_ENCOUNTER_RESULTS_CACHE_TIMEOUT_SECONDS,
    key_prefix=_encounter_results_cache_key,
)
def encounter_results() -> str:
    """Render encounter-level grading summaries."""

    page = request.args.get("page", default=1, type=int) or 1
    hospital_id = request.args.get("hospital_id", type=int)
    lab_unit_id = request.args.get("lab_unit_id", type=int)
    capture_date_str = (request.args.get("capture_date") or "").strip() or None
    start_date_str = (request.args.get("start_date") or "").strip() or None
    end_date_str = (request.args.get("end_date") or "").strip() or None
    selected_project_ids = [value for value in request.args.getlist("project_id") if value.isdigit()]
    project_ids = tuple(int(value) for value in selected_project_ids)
    include_classical_arg_present = "include_classical" in request.args
    include_classical = request.args.get("include_classical") == "1" if include_classical_arg_present else None
    capture_date = None
    if capture_date_str:
        capture_date = parse_date_yyyy_mm_dd(capture_date_str)
    start_date = parse_date_yyyy_mm_dd(start_date_str) if start_date_str else None
    end_date = parse_date_yyyy_mm_dd(end_date_str) if end_date_str else None

    page = max(1, page)
    per_page = current_app.config.get("REPORT_ENCOUNTER_RESULTS_PAGE_SIZE", 10)
    per_page = per_page if isinstance(per_page, int) and per_page > 0 else 10

    with get_db_session() as db:
        # Check if user has any access at all
        if not current_user.is_master_admin and not current_user.hospital_id:
            flash("No hospital access.", "warning")
            return redirect(url_for("home.index"))

        # Build scoped lab-unit set once, then drive encounter list from MV.
        scoped_lab_unit_ids = [
            row[0]
            for row in scope(
                db,
                db.query(LabUnit.id),
                LabUnit,
                current_user,
                "analytics.encounters.view",
            ).all()
        ]
        if not scoped_lab_unit_ids:
            total = 0
            encounters = []
            projects = []
        else:
            projects = (
                db.query(Project)
                .join(PatientEncounters, PatientEncounters.project_id == Project.id)
                .filter(PatientEncounters.lab_unit_id.in_(scoped_lab_unit_ids))
                .distinct()
                .order_by(Project.code, Project.title)
                .all()
            )
            mv_params: dict[str, Any] = {
                "scoped_lab_unit_ids": scoped_lab_unit_ids,
                "hospital_id": hospital_id,
                "lab_unit_id": lab_unit_id,
                "capture_date": capture_date,
                "start_date": start_date,
                "end_date": end_date,
                "project_ids": list(project_ids) or [-1],
                "include_classical": bool(include_classical),
                "has_source_filter": bool(project_ids or include_classical is not None),
                "limit": per_page,
                "offset": (page - 1) * per_page,
            }
            count_sql = sa.text(
                """
                SELECT COUNT(*)::int AS total
                FROM mvw_encounter_pivot ep
                WHERE ep.lab_unit_id IN :scoped_lab_unit_ids
                  AND (:hospital_id IS NULL OR ep.hospital_id = :hospital_id)
                  AND (:lab_unit_id IS NULL OR ep.lab_unit_id = :lab_unit_id)
                  AND (:capture_date IS NULL OR ep.capture_date = :capture_date)
                  AND (:start_date IS NULL OR ep.capture_date >= :start_date)
                  AND (:end_date IS NULL OR ep.capture_date <= :end_date)
                  AND (
                    :has_source_filter IS FALSE
                    OR EXISTS (
                      SELECT 1
                      FROM patient_encounters pe
                      WHERE pe.id = ep.encounter_id
                        AND (
                          (:include_classical IS TRUE AND pe.project_id IS NULL)
                          OR pe.project_id IN :project_ids
                        )
                    )
                  )
                """
            ).bindparams(
                sa.bindparam("scoped_lab_unit_ids", expanding=True),
                sa.bindparam("project_ids", expanding=True),
            )
            total = int((db.execute(count_sql, mv_params).scalar() or 0))

            page_sql = sa.text(
                """
                SELECT ep.encounter_id
                FROM mvw_encounter_pivot ep
                WHERE ep.lab_unit_id IN :scoped_lab_unit_ids
                  AND (:hospital_id IS NULL OR ep.hospital_id = :hospital_id)
                  AND (:lab_unit_id IS NULL OR ep.lab_unit_id = :lab_unit_id)
                  AND (:capture_date IS NULL OR ep.capture_date = :capture_date)
                  AND (:start_date IS NULL OR ep.capture_date >= :start_date)
                  AND (:end_date IS NULL OR ep.capture_date <= :end_date)
                  AND (
                    :has_source_filter IS FALSE
                    OR EXISTS (
                      SELECT 1
                      FROM patient_encounters pe
                      WHERE pe.id = ep.encounter_id
                        AND (
                          (:include_classical IS TRUE AND pe.project_id IS NULL)
                          OR pe.project_id IN :project_ids
                        )
                    )
                  )
                ORDER BY ep.capture_date DESC NULLS LAST, ep.encounter_id DESC
                LIMIT :limit OFFSET :offset
                """
            ).bindparams(
                sa.bindparam("scoped_lab_unit_ids", expanding=True),
                sa.bindparam("project_ids", expanding=True),
            )
            encounter_ids = [int(r[0]) for r in db.execute(page_sql, mv_params).all() if r and r[0] is not None]

            if encounter_ids:
                encounters = (
                    db.query(PatientEncounters)
                    .filter(PatientEncounters.id.in_(encounter_ids))
                    .options(
                        selectinload(PatientEncounters.lab_unit).selectinload(LabUnit.hospital),
                        selectinload(PatientEncounters.encounter_files),
                        selectinload(PatientEncounters.encounter_set_images).selectinload(EncounterSetImage.camera),
                        selectinload(PatientEncounters.glaucoma_results_cleaned),
                        selectinload(PatientEncounters.dr_reports),
                        selectinload(PatientEncounters.zip_file),
                    )
                    .all()
                )
                order_map = {enc_id: idx for idx, enc_id in enumerate(encounter_ids)}
                encounters.sort(key=lambda enc: order_map.get(enc.id, 10**9))
            else:
                encounters = []

        encounter_file_ids: list[int] = []
        encounter_set_image_ids: list[int] = []
        for encounter in encounters:
            for encounter_file in encounter.encounter_files:
                encounter_file_ids.append(encounter_file.id)
            for encounter_set_image in encounter.encounter_set_images:
                encounter_set_image_ids.append(encounter_set_image.id)

        task_details: list[dict[str, Any]] = []
        if encounter_file_ids or encounter_set_image_ids:
            # Scope the task query to what this user may read
            task_clauses = []
            if encounter_file_ids:
                task_clauses.append(GradingTask.encounter_file_id.in_(encounter_file_ids))
            if encounter_set_image_ids:
                task_clauses.append(GradingTask.encounter_set_image_id.in_(encounter_set_image_ids))
            task_query = db.query(GradingTask).filter(sa.or_(*task_clauses))
            task_query = scope(db, task_query, GradingTask, current_user, 'analytics.encounters.view')
            
            tasks = (
                task_query.options(
                    selectinload(GradingTask.disease),
                    selectinload(GradingTask.lab_unit).selectinload(LabUnit.hospital),
                    selectinload(GradingTask.encounter_file),
                    selectinload(GradingTask.encounter_set_image),
                    selectinload(GradingTask.direct_image),
                )
                .all()
            )
            task_details = fetch_image_task_details(db, tasks)

        encounter_rows = build_encounter_result_payload(encounters, task_details)

        # Filter hospitals and lab units to only those the user has access to
        lab_units_query = db.query(LabUnit)
        lab_units_query = scope(db, lab_units_query, LabUnit, current_user, 'analytics.encounters.view')
        lab_units = (
            lab_units_query
            .options(selectinload(LabUnit.hospital))
            .order_by(LabUnit.name)
            .all()
        )
        
        hospitals_query = db.query(Hospital)
        hospitals_query = scope(db, hospitals_query, Hospital, current_user, 'analytics.encounters.view')
        hospitals = (
            hospitals_query
            .order_by(Hospital.name)
            .all()
        )

        # Calculate pagination and URLs within the session context
        total_pages = max(1, math.ceil(total / per_page)) if total else 1
        filter_params = {
            "hospital_id": hospital_id,
            "lab_unit_id": lab_unit_id,
            "capture_date": capture_date_str,
            "start_date": start_date_str,
            "end_date": end_date_str,
            "project_id": list(project_ids),
            "include_classical": "1" if include_classical else None,
        }

        prev_url = (
            url_for("analytics.encounter_results", **(_filter_query_params(filter_params) | {"page": page - 1}))
            if page > 1
            else None
        )
        next_url = (
            url_for("analytics.encounter_results", **(_filter_query_params(filter_params) | {"page": page + 1}))
            if page < total_pages
            else None
        )
        export_url = url_for(
            "fundus_api.export_encounter_task_results",
            **_filter_query_params(filter_params),
        )

        # Render template while session is still active
        return render_template(
            "analytics/results_encounters.html",
            encounters=encounter_rows,
            hospitals=hospitals,
            lab_units=lab_units,
            projects=projects,
            filters=filter_params,
            page=page,
            total_pages=total_pages,
            prev_url=prev_url,
            next_url=next_url,
            export_url=export_url,
            total=total,
            per_page=per_page,
        )
