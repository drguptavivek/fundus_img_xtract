"""Routes for images without tasks."""

from __future__ import annotations

from datetime import datetime, time, timezone
from typing import Any

from flask import current_app, render_template, request, url_for
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
    DirectImageVerify,
    EncounterFile,
    GlaucomaResultsCleaned,
    GradingTask,
    Hospital,
    LabUnit,
    PatientEncounters,
)
from db_transaction_manager import get_db_session
from analytics.utils import build_encounter_result_payload, fetch_image_task_details
from utils.hospital_scoping import apply_scoping


@bp.route("/images-without-tasks", methods=["GET", "POST"])
@roles_required("admin", "local_admin", "data_manager", "analytics_viewer")
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

    with get_db_session() as db:
        hospitals: list[Hospital] = []
        lab_units: list[LabUnit] = []
        cameras: list[Camera] = []
        diseases_all: list[Disease] = []
        areas: list[Area] = []
        
        records: list[dict[str, Any]] = []


        if image_type in {"all", "zip"}:
            encounter_query = (
                db.query(EncounterFile)
                .outerjoin(GradingTask, GradingTask.encounter_file_id == EncounterFile.id)
                .filter(EncounterFile.file_type == 'image')
                .filter(GradingTask.id.is_(None))
            )
            
            # Apply hospital scoping for zip images
            encounter_query = apply_scoping(encounter_query, EncounterFile, current_user, 'analytics')
            
            encounter_query = encounter_query.options(
                selectinload(EncounterFile.lab_unit).selectinload(LabUnit.hospital),
                selectinload(EncounterFile.patient_encounter)
                .selectinload(PatientEncounters.lab_unit)
                .selectinload(LabUnit.hospital),
            )
            
            encounter_rows = encounter_query.all()

            for ef in encounter_rows:
                lab_unit = ef.lab_unit or (ef.patient_encounter.lab_unit if ef.patient_encounter else None)
                
                # Filter by specific lab_unit if requested
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
            direct_query = (
                db.query(DirectImageUpload)
                .outerjoin(GradingTask, GradingTask.direct_image_upload_id == DirectImageUpload.id)
                .filter(GradingTask.id.is_(None))
            )
            
            # Apply hospital scoping for direct uploads
            direct_query = apply_scoping(direct_query, DirectImageUpload, current_user, 'analytics')
            
            direct_query = direct_query.options(selectinload(DirectImageUpload.lab_unit).selectinload(LabUnit.hospital))
            
            direct_rows = direct_query.all()
            direct_ids = [upload.id for upload in direct_rows]
            verification_by_upload_id: dict[int, str] = {}
            if direct_ids:
                verification_rows = (
                    db.query(DirectImageVerify.image_upload_id, DirectImageVerify.verified_status)
                    .filter(DirectImageVerify.image_upload_id.in_(direct_ids))
                    .all()
                )
                verification_by_upload_id = {
                    image_upload_id: verified_status
                    for image_upload_id, verified_status in verification_rows
                }

            for upload in direct_rows:
                lab_unit = upload.lab_unit
                
                # Filter check for the specific lab_unit filter
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
                        "verification_status": verification_by_upload_id.get(upload.id),
                        "encounter_id": None,
                        "view_url": url_for("analytics.view_direct_image", uuid_str=upload.uuid),
                        "edit_url": url_for("preprocess.anonymize_image", uuid=upload.uuid),
                    }
                )

        # Normalize datetimes for comparison - handle both timezone-aware and naive datetimes
        def normalize_datetime(dt):
            if dt is None:
                return datetime.min
            # If datetime is timezone-aware, convert to naive for consistent comparison
            if hasattr(dt, 'tzinfo') and dt.tzinfo is not None:
                return dt.replace(tzinfo=None)
            return dt

        records.sort(key=lambda item: normalize_datetime(item.get("record_date")), reverse=True)
        total = len(records)
        start = (page - 1) * per_page
        end = start + per_page
        page_records = records[start:end]

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
            
        # Extract hospital and lab unit data before session closes
        hospitals_data = [
            {
                "id": hospital.id,
                "name": hospital.name,
            }
            for hospital in hospitals
        ]
        
        lab_units_data = [
            {
                "id": lu.id,
                "name": lu.name,
                "hospital": {
                    "id": lu.hospital.id if lu.hospital else None,
                    "name": lu.hospital.name if lu.hospital else None,
                } if lu.hospital else None,
            }
            for lu in lab_units
        ]

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
        hospitals=hospitals_data,
        lab_units=lab_units_data,
    )
