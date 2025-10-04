"""Routes for images without tasks."""

from __future__ import annotations

from datetime import datetime, time, timezone
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


@bp.route("/images/no-tasks", methods=["GET"])
@roles_required("admin", "data_manager", "optometrist")
def images_without_tasks() -> str:
    """Display images that have no associated grading tasks."""

    page = request.args.get("page", default=1, type=int) or 1
    image_type = (request.args.get("type") or "all").strip().lower()
    if image_type not in {"all", "zip", "direct"}:
        image_type = "all"
    lab_unit_id = request.args.get("lab_unit_id", type=int)

    page = max(1, page)
    per_page = current_app.config.get("RESULTS_NO_TASK_PAGE_SIZE", 50)
    per_page = per_page if isinstance(per_page, int) and per_page > 0 else 50

    db = Session()
    hospitals: list[Hospital] = []
    lab_units: list[LabUnit] = []
    cameras: list[Camera] = []
    diseases_all: list[Disease] = []
    areas: list[Area] = []
    try:
        records: list[dict[str, Any]] = []

        if image_type in {"all", "zip"}:
            encounter_rows = (
                db.query(EncounterFile)
                .outerjoin(GradingTask, GradingTask.encounter_file_id == EncounterFile.id)
                .filter(EncounterFile.file_type == 'image')
                .filter(GradingTask.id.is_(None))
                .options(
                    selectinload(EncounterFile.lab_unit).selectinload(LabUnit.hospital),
                    selectinload(EncounterFile.patient_encounter)
                    .selectinload(PatientEncounters.lab_unit)
                    .selectinload(LabUnit.hospital),
                )
                .all()
            )

            for ef in encounter_rows:
                lab_unit = ef.lab_unit or (ef.patient_encounter.lab_unit if ef.patient_encounter else None)
                if lab_unit_id and (not lab_unit or lab_unit.id != lab_unit_id):
                    continue

                capture_dt: datetime | None = None
                if ef.patient_encounter and ef.patient_encounter.capture_date_dt:
                    capture_dt = datetime.combine(ef.patient_encounter.capture_date_dt, datetime.min.time())
                elif ef.patient_encounter and ef.patient_encounter.capture_date:
                    try:
                        capture_dt = datetime.fromisoformat(ef.patient_encounter.capture_date)
                    except Exception:
                        capture_dt = None

                records.append(
                    {
                        "uuid": ef.uuid,
                        "source": "zip",
                        "lab_unit_name": lab_unit.name if lab_unit else None,
                        "hospital_name": lab_unit.hospital.name if lab_unit and lab_unit.hospital else None,
                        "record_date": capture_dt,
                        "date_display": ef.patient_encounter.capture_date_dt if ef.patient_encounter else None,
                        "encounter_id": ef.patient_encounter_id,
                        "view_url": url_for("verify_remedio_nodr.nodr_edit", encounter_id=ef.patient_encounter_id) if ef.patient_encounter_id else None,
                    }
                )

        if image_type in {"all", "direct"}:
            direct_rows = (
                db.query(DirectImageUpload)
                .outerjoin(GradingTask, GradingTask.direct_image_upload_id == DirectImageUpload.id)
                .filter(GradingTask.id.is_(None))
                .options(selectinload(DirectImageUpload.lab_unit).selectinload(LabUnit.hospital))
                .all()
            )

            for upload in direct_rows:
                lab_unit = upload.lab_unit
                if lab_unit_id and (not lab_unit or lab_unit.id != lab_unit_id):
                    continue

                records.append(
                    {
                        "uuid": upload.uuid,
                        "source": "direct",
                        "lab_unit_name": lab_unit.name if lab_unit else None,
                        "hospital_name": lab_unit.hospital.name if lab_unit and lab_unit.hospital else None,
                        "record_date": upload.created_at,
                        "date_display": upload.created_at.date() if upload.created_at else None,
                        "encounter_id": None,
                        "view_url": url_for("analytics.view_upload", uuid_str=upload.uuid),
                    }
                )

        records.sort(key=lambda item: item.get("record_date") or datetime.min, reverse=True)
        total = len(records)
        start = (page - 1) * per_page
        end = start + per_page
        page_records = records[start:end]

        hospitals = db.query(Hospital).order_by(Hospital.name).all()
        lab_units = db.query(LabUnit).order_by(LabUnit.name).all()

    finally:
        db.close()

    total_pages = max(1, (total + per_page - 1) // per_page) if total else 1
    filter_params = {
        "type": image_type,
        "lab_unit_id": lab_unit_id,
    }

    def _filter_kwargs(target_page: int) -> dict[str, Any]:
        params: dict[str, Any] = {"page": target_page}
        if image_type != "all":
            params["type"] = image_type
        if lab_unit_id:
            params["lab_unit_id"] = lab_unit_id
        return params

    prev_url = url_for("analytics.images_without_tasks", **_filter_kwargs(page - 1)) if page > 1 else None
    next_url = url_for("analytics.images_without_tasks", **_filter_kwargs(page + 1)) if page < total_pages else None

    return render_template(
        "analytics/no_task_images.html",
        rows=page_records,
        page=page,
        total=total,
        total_pages=total_pages,
        prev_url=prev_url,
        next_url=next_url,
        filters=filter_params,
        hospitals=hospitals,
        lab_units=lab_units,
    )