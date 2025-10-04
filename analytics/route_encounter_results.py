"""Routes for encounter results."""

from __future__ import annotations

import math
from datetime import datetime, date as _date, time, timezone
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


def _parse_date(value: str | None) -> _date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _normalize_datetime(value: datetime | _date | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, _date):
        return datetime.combine(value, time.min, timezone.utc)
    return None


@bp.route("/encounters", methods=["GET"])
@roles_required("admin", "data_manager")
def encounter_results() -> str:
    """Render encounter-level grading summaries."""

    page = request.args.get("page", default=1, type=int) or 1
    hospital_id = request.args.get("hospital_id", type=int)
    lab_unit_id = request.args.get("lab_unit_id", type=int)
    capture_date_str = (request.args.get("capture_date") or "").strip() or None
    capture_date = None
    if capture_date_str:
        try:
            capture_date = datetime.strptime(capture_date_str, "%Y-%m-%d").date()
        except ValueError:
            capture_date = None

    page = max(1, page)
    per_page = current_app.config.get("REPORT_ENCOUNTER_RESULTS_PAGE_SIZE", 10)
    per_page = per_page if isinstance(per_page, int) and per_page > 0 else 10

    db = Session()
    try:
        query = (
            db.query(PatientEncounters)
            .outerjoin(LabUnit, PatientEncounters.lab_unit)
            .outerjoin(Hospital, LabUnit.hospital)
            .options(
                selectinload(PatientEncounters.lab_unit).selectinload(LabUnit.hospital),
                selectinload(PatientEncounters.encounter_files)
                .selectinload(EncounterFile.gradings),
                selectinload(PatientEncounters.glaucoma_results_cleaned),
                selectinload(PatientEncounters.dr_reports),
                selectinload(PatientEncounters.zip_file),
            )
        )

        if hospital_id:
            query = query.filter(LabUnit.hospital_id == hospital_id)

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
            tasks = (
                db.query(GradingTask)
                .filter(GradingTask.encounter_file_id.in_(encounter_file_ids))
                .options(
                    selectinload(GradingTask.disease),
                    selectinload(GradingTask.lab_unit).selectinload(LabUnit.hospital),
                    selectinload(GradingTask.encounter_file),
                    selectinload(GradingTask.direct_image),
                )
                .all()
            )
            task_details = fetch_image_task_details(db, tasks)

        encounter_rows = build_encounter_result_payload(encounters, task_details)

        hospitals = db.query(Hospital).order_by(Hospital.name).all()
        lab_units = db.query(LabUnit).options(selectinload(LabUnit.hospital)).order_by(LabUnit.name).all()

    finally:
        db.close()

    total_pages = max(1, math.ceil(total / per_page)) if total else 1
    filter_params = {
        "hospital_id": hospital_id,
        "lab_unit_id": lab_unit_id,
        "capture_date": capture_date_str,
    }

    def _enc_filter_kwargs(target_page: int) -> dict[str, int | str]:
        params: dict[str, int | str] = {"page": target_page}
        for key, value in filter_params.items():
            if not value:
                continue
            params[key] = value
        return params

    prev_url = url_for("analytics.encounter_results", **_enc_filter_kwargs(page - 1)) if page > 1 else None
    next_url = url_for("analytics.encounter_results", **_enc_filter_kwargs(page + 1)) if page < total_pages else None

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