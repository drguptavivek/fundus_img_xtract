"""Routes for image results."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from flask import current_app, render_template, request, url_for
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
    Session,
)
from analytics.utils import build_encounter_result_payload, fetch_image_task_details

TASK_STATE_OPTIONS: tuple[str, ...] = (
    "pending",
    "resident_done",
    "faculty_done",
    "arbitration",
    "final",
)


@bp.route("/images", methods=["GET"])
@roles_required("admin", "data_manager")
def image_results() -> str:
    """Render per-image grading results with filtering and pagination."""

    page = request.args.get("page", default=1, type=int) or 1
    disease_id = request.args.get("disease_id", type=int)
    upload_type = (request.args.get("upload_type") or "").strip().lower() or None
    hospital_id = request.args.get("hospital_id", type=int)
    lab_unit_id = request.args.get("lab_unit_id", type=int)
    task_state = (request.args.get("task_state") or "").strip().lower() or None
    if task_state not in TASK_STATE_OPTIONS:
        task_state = None

    page = max(1, page)
    per_page = current_app.config.get("REPORT_IMAGE_RESULTS_PAGE_SIZE", 50)
    per_page = per_page if isinstance(per_page, int) and per_page > 0 else 50

    db = Session()
    try:
        query = db.query(GradingTask).join(LabUnit, GradingTask.lab_unit).join(Hospital, LabUnit.hospital)

        if disease_id:
            query = query.filter(GradingTask.disease_id == disease_id)

        if upload_type in {"zip", "direct"}:
            if upload_type == "zip":
                query = query.filter(GradingTask.encounter_file_id.isnot(None))
            else:
                query = query.filter(GradingTask.direct_image_upload_id.isnot(None))

        if hospital_id:
            query = query.filter(LabUnit.hospital_id == hospital_id)

        if lab_unit_id:
            query = query.filter(GradingTask.lab_unit_id == lab_unit_id)

        if task_state and task_state in TASK_STATE_OPTIONS:
            query = query.filter(GradingTask.state == task_state)

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

        rows = fetch_image_task_details(db, tasks)

        diseases = db.query(Disease).order_by(Disease.name).all()
        hospitals = db.query(Hospital).order_by(Hospital.name).all()
        lab_units = db.query(LabUnit).options(selectinload(LabUnit.hospital)).order_by(LabUnit.name).all()

    finally:
        db.close()

    total_pages = max(1, math.ceil(total / per_page)) if total else 1
    filter_params = {
        "disease_id": disease_id,
        "upload_type": upload_type,
        "hospital_id": hospital_id,
        "lab_unit_id": lab_unit_id,
        "task_state": task_state,
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