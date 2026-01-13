"""Routes for encounter results."""

from __future__ import annotations

import math
from datetime import datetime, date as _date, time, timezone
from typing import Any

from flask import current_app, render_template, request, url_for, flash, redirect
from flask_login import current_user
from auth.roles import roles_required
from sqlalchemy.orm import selectinload

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


@bp.route("/encounters", methods=["GET"])
@roles_required(
    "admin",
    "local_admin",
    "fileUploader",
    "ophthalmologist",
    "data_manager",
    "resident",
    "optometrist",
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
        # Determine scoping context
        query = db.query(PatientEncounters)
        query = apply_scoping(query, PatientEncounters, current_user, 'analytics')
        
        # Check if user has any access at all
        if not current_user.is_master_admin and not current_user.hospital_id:
            flash("No hospital access.", "warning")
            return redirect(url_for("home.index"))
        
        # Apply options for relationships
        query = query.outerjoin(LabUnit, PatientEncounters.lab_unit).outerjoin(Hospital, LabUnit.hospital).options(
            selectinload(PatientEncounters.lab_unit).selectinload(LabUnit.hospital),
            selectinload(PatientEncounters.encounter_files),
            selectinload(PatientEncounters.glaucoma_results_cleaned),
            selectinload(PatientEncounters.dr_reports),
            selectinload(PatientEncounters.zip_file),
        )

        if hospital_id:
            # Re-apply scoping to hospital filter check? 
            # Actually apply_scoping already filters by hospital if user is scoped.
            # If they pass a specific hospital_id, we just filter by it.
            # If it's NOT their hospital, the previous scoping will result in empty set.
            query = query.filter(LabUnit.hospital_id == hospital_id)

        # Only allow filtering by lab_unit_id if the user has access to that lab unit
        if lab_unit_id:
            query = query.filter(PatientEncounters.lab_unit_id == lab_unit_id)

        if capture_date:
            query = query.filter(PatientEncounters.capture_date_dt == capture_date)

        total = query.count()

        encounters = (
            query.order_by(PatientEncounters.capture_date_dt.desc().nullslast(), PatientEncounters.id.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )

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

        # Determine PII masking
        mask_pii = False
        if encounters:
            # Check the first encounter's hospital for masking decision
            first_enc = encounters[0]
            data_hospital_id = first_enc.lab_unit.hospital_id if first_enc.lab_unit else None
            mask_pii = should_mask_pii(
                current_user_hospital_id=current_user.hospital_id,
                data_hospital_id=data_hospital_id,
                current_user_role=current_user.roles[0].name if current_user.roles else None
            )

        encounter_rows = build_encounter_result_payload(encounters, task_details, mask_pii=mask_pii)

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
