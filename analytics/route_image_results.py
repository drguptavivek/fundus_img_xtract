"""Routes for image results."""

from __future__ import annotations

import math
from datetime import datetime, timezone
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
    Grade,
    GradingTask,
    Hospital,
    LabUnit,
    PatientEncounters,
)
from db_transaction_manager import get_db_session
from analytics.utils import build_encounter_result_payload, fetch_image_task_details
from utils.upload_eligibility import get_user_lab_unit_ids_no_admin_override

TASK_STATE_OPTIONS: tuple[str, ...] = (
    "pending",
    "resident_done",
    "resident2_done",
    "arbitration",
    "final",
)


@bp.route("/images", methods=["GET"])
@roles_required(
    "admin",
    "local_admin",
    "fileUploader",
    "ophthalmologist",
    "data_manager",
    "resident",
    "optometrist",
)
def image_results() -> str:
    """Render per-image grading results with filtering and pagination."""

    page = request.args.get("page", default=1, type=int) or 1
    disease_id = request.args.get("disease_id", type=int)
    upload_type = (request.args.get("upload_type") or "").strip().lower() or None
    hospital_id = request.args.get("hospital_id", type=int)
    lab_unit_id = request.args.get("lab_unit_id", type=int)
    task_state = (request.args.get("task_state") or "").strip().lower() or None
    has_ai_grade = request.args.get("has_ai_grade", type=lambda x: x.lower() == 'true') # Accept 'true' or 'false' as string, convert to boolean
    if has_ai_grade is None: # If the parameter is not present or not 'true'/'false', default to None (no filter)
        has_ai_grade = request.args.get("has_ai_grade", type=lambda x: x.lower() == 'false')
        if has_ai_grade is not None:
            has_ai_grade = not has_ai_grade # If original was 'false', we want the flag to be False, so invert again
        else:
            has_ai_grade = None # Reset if it was a non-boolean string
    if task_state not in TASK_STATE_OPTIONS:
        task_state = None

    page = max(1, page)
    per_page = current_app.config.get("REPORT_IMAGE_RESULTS_PAGE_SIZE", 50)
    per_page = per_page if isinstance(per_page, int) and per_page > 0 else 50

    with get_db_session() as db:
        # Check user permissions for lab unit access (no admin override)
        user_lab_unit_ids = set(get_user_lab_unit_ids_no_admin_override(current_user.id) or [])
        if not user_lab_unit_ids:
            flash("No lab unit access.", "warning")
            return redirect(url_for("home.index"))
        allowed_hospital_ids = {
            hid for hid, in db.query(LabUnit.hospital_id).filter(LabUnit.id.in_(user_lab_unit_ids))
            if hid is not None
        }
        
        query = (
            db.query(GradingTask)
            .join(LabUnit, GradingTask.lab_unit)
            .join(Hospital, LabUnit.hospital)
            .filter(GradingTask.lab_unit_id.in_(user_lab_unit_ids))
        )

        if disease_id:
            query = query.filter(GradingTask.disease_id == disease_id)

        if upload_type in {"zip", "direct"}:
            if upload_type == "zip":
                query = query.filter(GradingTask.encounter_file_id.isnot(None))
            else:
                query = query.filter(GradingTask.direct_image_upload_id.isnot(None))

        if hospital_id:
            if hospital_id not in allowed_hospital_ids:
                from flask import abort
                abort(403, description="Access denied to this hospital")
            query = query.filter(LabUnit.hospital_id == hospital_id)

        # Only allow filtering by lab_unit_id if the user has access to that lab unit
        if lab_unit_id:
            if lab_unit_id not in user_lab_unit_ids:
                from flask import abort
                abort(403, description="Access denied to this lab unit")
            query = query.filter(GradingTask.lab_unit_id == lab_unit_id)

        if task_state and task_state in TASK_STATE_OPTIONS:
            query = query.filter(GradingTask.state == task_state)
            
        # Apply filter for presence of AI grades
        # This requires a join or subquery to check for associated AI grades (either AIGrade or Grade with role_slot='ai')
        if has_ai_grade is not None:
            from sqlalchemy import exists
            # Check for AIGrade records linked to the image (via encounter_file_id or direct_image_upload_id) and disease
   
            # Check for Grade records with role_slot='ai' linked to the task
            ai_grade_from_grade_exists_subq = exists().where(
                Grade.task_id == GradingTask.id,
                Grade.role_slot == 'ai'
            ).correlate(GradingTask)
            
            if has_ai_grade: # Filter for tasks that *have* AI grades
                query = query.filter(
                    ai_grade_from_grade_exists_subq
                )
            else: # Filter for tasks that *do not have* AI grades
                query = query.filter(
                    ~ai_grade_from_grade_exists_subq
                )

        total = query.count()

        offset = (page - 1) * per_page
        tasks = (
            query.options(
                selectinload(GradingTask.disease),
                selectinload(GradingTask.lab_unit).selectinload(LabUnit.hospital),
                selectinload(GradingTask.encounter_file),
                selectinload(GradingTask.direct_image),
            )
            .order_by(GradingTask.updated_at.desc())
            .offset(offset)
            .limit(per_page)
            .all()
        )

        # Filter lab units to only those the user has access to
        lab_units_query = (
            db.query(LabUnit)
            .filter(LabUnit.id.in_(list(user_lab_unit_ids)))
            .options(selectinload(LabUnit.hospital))
            .order_by(LabUnit.name)
            .all()
        )

        # Convert to simple data structures to avoid session issues in templates
        diseases = [
            {"id": d.id, "name": d.name}
            for d in db.query(Disease)
            .join(GradingTask, GradingTask.disease_id == Disease.id)
            .filter(GradingTask.lab_unit_id.in_(user_lab_unit_ids))
            .distinct()
            .order_by(Disease.name)
            .all()
        ]
        hospitals = [
            {"id": h.id, "name": h.name}
            for h in db.query(Hospital)
            .join(LabUnit, LabUnit.hospital_id == Hospital.id)
            .filter(LabUnit.id.in_(user_lab_unit_ids))
            .distinct()
            .order_by(Hospital.name)
            .all()
        ]
        lab_units = [
            {"id": lu.id, "name": lu.name, "hospital_id": lu.hospital_id, "hospital_name": lu.hospital.name if lu.hospital else None}
            for lu in lab_units_query
        ]
        rows = fetch_image_task_details(db, tasks)

    total_pages = max(1, math.ceil(total / per_page)) if total else 1
    filter_params = {
        "disease_id": disease_id,
        "upload_type": upload_type,
        "hospital_id": hospital_id,
        "lab_unit_id": lab_unit_id,
        "task_state": task_state,
        "has_ai_grade": 'true' if has_ai_grade else 'false' if has_ai_grade is False else None,
    }

    def _filter_kwargs(target_page: int) -> dict[str, int | str]:
        params: dict[str, int | str] = {"page": target_page}
        for key, value in filter_params.items():
            if value is None:
                continue
            if isinstance(value, int) and value == 0:
                continue
            if isinstance(value, str) and value == "":
                continue
            params[key] = value
        return params

    prev_url = url_for("analytics.image_results", **_filter_kwargs(page - 1)) if page > 1 else None
    next_url = url_for("analytics.image_results", **_filter_kwargs(page + 1)) if page < total_pages else None

    return render_template(
        "analytics/results_images.html",
        rows=rows,
        diseases=diseases,
        hospitals=hospitals,
        lab_units=lab_units,
        task_state_options=TASK_STATE_OPTIONS,
        filters=filter_params,
        page=page,
        total_pages=total_pages,
        prev_url=prev_url,
        next_url=next_url,
        total=total,
        per_page=per_page,
    )
