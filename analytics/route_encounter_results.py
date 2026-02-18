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
    GlaucomaResultsCleaned,
    GradingTask,
    Hospital,
    LabUnit,
    PatientEncounters,
)
from db_transaction_manager import get_db_session
from analytics.utils import build_encounter_result_payload, fetch_image_task_details, build_pagination_params
from utils.hospital_scoping import apply_scoping
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


def _encounter_results_cache_key() -> str:
    return f"analytics:encounters:u{current_user.id}:{request.query_string.decode('utf-8')}"


@bp.route("/encounters", methods=["GET"])
@roles_required(
    "admin",
    "local_admin",
    "fileUploader",
    "ophthalmologist",
    "data_manager",
    "analytics_viewer",
    "resident",
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
    capture_date = None
    if capture_date_str:
        capture_date = parse_date_yyyy_mm_dd(capture_date_str)

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
            for row in apply_scoping(
                db.query(LabUnit.id),
                LabUnit,
                current_user,
                "analytics",
            ).all()
        ]
        if not scoped_lab_unit_ids:
            total = 0
            encounters = []
        else:
            mv_params: dict[str, Any] = {
                "scoped_lab_unit_ids": scoped_lab_unit_ids,
                "hospital_id": hospital_id,
                "lab_unit_id": lab_unit_id,
                "capture_date": capture_date,
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
                """
            ).bindparams(sa.bindparam("scoped_lab_unit_ids", expanding=True))
            total = int((db.execute(count_sql, mv_params).scalar() or 0))

            page_sql = sa.text(
                """
                SELECT ep.encounter_id
                FROM mvw_encounter_pivot ep
                WHERE ep.lab_unit_id IN :scoped_lab_unit_ids
                  AND (:hospital_id IS NULL OR ep.hospital_id = :hospital_id)
                  AND (:lab_unit_id IS NULL OR ep.lab_unit_id = :lab_unit_id)
                  AND (:capture_date IS NULL OR ep.capture_date = :capture_date)
                ORDER BY ep.capture_date DESC NULLS LAST, ep.encounter_id DESC
                LIMIT :limit OFFSET :offset
                """
            ).bindparams(sa.bindparam("scoped_lab_unit_ids", expanding=True))
            encounter_ids = [int(r[0]) for r in db.execute(page_sql, mv_params).all() if r and r[0] is not None]

            if encounter_ids:
                encounters = (
                    db.query(PatientEncounters)
                    .filter(PatientEncounters.id.in_(encounter_ids))
                    .options(
                        selectinload(PatientEncounters.lab_unit).selectinload(LabUnit.hospital),
                        selectinload(PatientEncounters.encounter_files),
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
        for encounter in encounters:
            for encounter_file in encounter.encounter_files:
                encounter_file_ids.append(encounter_file.id)

        task_details: list[dict[str, Any]] = []
        if encounter_file_ids:
            # Apply apply_scoping to task query
            task_query = db.query(GradingTask).filter(GradingTask.encounter_file_id.in_(encounter_file_ids))
            task_query = apply_scoping(task_query, GradingTask, current_user, 'analytics')
            
            tasks = (
                task_query.options(
                    selectinload(GradingTask.disease),
                    selectinload(GradingTask.lab_unit).selectinload(LabUnit.hospital),
                    selectinload(GradingTask.encounter_file),
                    selectinload(GradingTask.direct_image),
                )
                .all()
            )
            task_details = fetch_image_task_details(db, tasks)

        encounter_rows = build_encounter_result_payload(encounters, task_details)

        # Filter hospitals and lab units to only those the user has access to
        lab_units_query = db.query(LabUnit)
        lab_units_query = apply_scoping(lab_units_query, LabUnit, current_user, 'analytics')
        lab_units = (
            lab_units_query
            .options(selectinload(LabUnit.hospital))
            .order_by(LabUnit.name)
            .all()
        )
        
        hospitals_query = db.query(Hospital)
        hospitals_query = apply_scoping(hospitals_query, Hospital, current_user, 'analytics')
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
        }

        prev_url = (
            url_for("analytics.encounter_results", **build_pagination_params(filter_params, page - 1))
            if page > 1
            else None
        )
        next_url = (
            url_for("analytics.encounter_results", **build_pagination_params(filter_params, page + 1))
            if page < total_pages
            else None
        )

        # Render template while session is still active
        return render_template(
            "analytics/results_encounters.html",
            encounters=encounter_rows,
            hospitals=hospitals,
            lab_units=lab_units,
            filters=filter_params,
            page=page,
            total_pages=total_pages,
            prev_url=prev_url,
            next_url=next_url,
            total=total,
            per_page=per_page,
        )
