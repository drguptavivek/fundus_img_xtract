"""Routes for search images."""

from __future__ import annotations

from datetime import datetime, date as _date, time, timezone
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
    EncounterFile,
    GlaucomaResultsCleaned,
    GradingTask,
    Hospital,
    LabUnit,
    PatientEncounters,
    Session,
)
from analytics.utils import build_encounter_result_payload, fetch_image_task_details
from utils.upload_eligibility import get_user_lab_unit_ids


def _parse_bool_param(value: str | None) -> bool | None:
    if value is None or value == "":
        return None
    lowered = value.strip().lower()
    if lowered in {"all", "any", "*"}:
        return None
    if lowered in {"1", "true", "yes", "y"}:
        return True
    if lowered in {"0", "false", "no", "n"}:
        return False
    return None


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


@bp.route("/images/search", methods=["GET"])
@bp.route("/images/search/", methods=["GET"])
@roles_required("admin", "data_manager", "optometrist")
def search_images() -> str:
    page = request.args.get("page", default=1, type=int) or 1
    source = (request.args.get("source") or "all").strip().lower()
    if source not in {"all", "zip", "direct"}:
        source = "all"

    hospital_id = request.args.get("hospital_id", type=int)
    lab_unit_id = request.args.get("lab_unit_id", type=int)
    camera_id = request.args.get("camera_id", type=int)
    disease_id = request.args.get("disease_id", type=int)
    area_id = request.args.get("area_id", type=int)
    is_mydriatic = _parse_bool_param(request.args.get("is_mydriatic"))

    has_encounter = _parse_bool_param(request.args.get("has_encounter"))
    has_dr_report = _parse_bool_param(request.args.get("has_dr_report"))
    has_glaucoma_report = _parse_bool_param(request.args.get("has_glaucoma_report"))

    upload_start = _parse_date(request.args.get("upload_start"))
    upload_end = _parse_date(request.args.get("upload_end"))
    capture_start = _parse_date(request.args.get("capture_start"))
    capture_end = _parse_date(request.args.get("capture_end"))

    page = max(1, page)
    per_page = current_app.config.get("ANALYTICS_SEARCH_IMAGES_PAGE_SIZE", 50)
    per_page = per_page if isinstance(per_page, int) and per_page > 0 else 50

    db = Session()
    try:
        # Check user permissions for lab unit access
        user_lab_unit_ids = get_user_lab_unit_ids(current_user.id)
        is_admin_like = current_user.has_role("admin", "data_manager", "optometrist")
        
        records: list[dict[str, Any]] = []

        upload_start_dt = datetime.combine(upload_start, time.min, timezone.utc) if upload_start else None
        upload_end_dt = datetime.combine(upload_end, time.max, timezone.utc) if upload_end else None

        if source in {"all", "zip"}:
            encounter_query = (
                db.query(EncounterFile)
                .join(PatientEncounters, EncounterFile.patient_encounter_id == PatientEncounters.id)
                .outerjoin(LabUnit, PatientEncounters.lab_unit)
                .outerjoin(Hospital, LabUnit.hospital)
                .outerjoin(DiabeticRetinopathyReport, DiabeticRetinopathyReport.patient_encounter_id == PatientEncounters.id)
                .outerjoin(GlaucomaResultsCleaned, GlaucomaResultsCleaned.patient_encounter_id == PatientEncounters.id)
                .filter(EncounterFile.file_type == 'image')
                .options(
                    selectinload(EncounterFile.patient_encounter)
                    .selectinload(PatientEncounters.dr_reports),
                    selectinload(EncounterFile.patient_encounter)
                    .selectinload(PatientEncounters.glaucoma_results_cleaned),
                    selectinload(EncounterFile.patient_encounter)
                    .selectinload(PatientEncounters.lab_unit)
                    .selectinload(LabUnit.hospital),
                )
            )
            
            # Apply lab unit access control for zip images
            if not is_admin_like and user_lab_unit_ids:
                encounter_query = encounter_query.filter(PatientEncounters.lab_unit_id.in_(list(user_lab_unit_ids)))

            if hospital_id:
                encounter_query = encounter_query.filter(Hospital.id == hospital_id)
            # Only allow filtering by lab_unit_id if the user has access to that lab unit
            if lab_unit_id:
                if not is_admin_like and lab_unit_id not in user_lab_unit_ids:
                    from flask import abort
                    abort(403, description="Access denied to this lab unit")
                encounter_query = encounter_query.filter(PatientEncounters.lab_unit_id == lab_unit_id)
            if capture_start:
                encounter_query = encounter_query.filter(PatientEncounters.capture_date_dt >= capture_start)
            if capture_end:
                encounter_query = encounter_query.filter(PatientEncounters.capture_date_dt <= capture_end)
            if upload_start:
                encounter_query = encounter_query.filter(PatientEncounters.capture_date_dt >= upload_start)
            if upload_end:
                encounter_query = encounter_query.filter(PatientEncounters.capture_date_dt <= upload_end)

            encounter_files = encounter_query.all()

            for ef in encounter_files:
                encounter = ef.patient_encounter
                lab_unit = encounter.lab_unit if encounter else None
                hospital = lab_unit.hospital if lab_unit and lab_unit.hospital else None

                has_enc = encounter is not None
                has_dr = bool(encounter and encounter.dr_reports)
                has_glaucoma = bool(encounter and encounter.glaucoma_results_cleaned)

                if has_encounter is not None and has_encounter != has_enc:
                    continue
                if has_dr_report is not None and has_dr_report != has_dr:
                    continue
                if has_glaucoma_report is not None and has_glaucoma_report != has_glaucoma:
                    continue

                capture_dt = None
                if encounter and encounter.capture_date_dt:
                    capture_dt = _normalize_datetime(encounter.capture_date_dt)
                elif encounter and encounter.capture_date:
                    try:
                        capture_dt = _normalize_datetime(datetime.fromisoformat(encounter.capture_date))
                    except ValueError:
                        capture_dt = None

                if capture_start and capture_dt and capture_dt.date() < capture_start:
                    continue
                if capture_end and capture_dt and capture_dt.date() > capture_end:
                    continue

                if is_mydriatic is not None:
                    continue

                view_url = url_for("analytics.view_encounter", encounter_id=encounter.id) if encounter else None

                records.append(
                    {
                        "uuid": ef.uuid,
                        "source": "zip",
                        "hospital_name": hospital.name if hospital else None,
                        "lab_unit_name": lab_unit.name if lab_unit else None,
                        "camera_name": None,
                        "disease_name": None,
                        "area_name": None,
                        "record_date": capture_dt,
                        "created_at": capture_dt,
                        "capture_date": encounter.capture_date_dt if encounter else None,
                        "encounter_id": encounter.id if encounter else None,
                        "has_dr": has_dr,
                        "has_glaucoma": has_glaucoma,
                        "view_url": view_url,
                        "is_mydriatic": None,
                    }
                )

        if source in {"all", "direct"}:
            direct_query = (
                db.query(DirectImageUpload)
                .options(
                    selectinload(DirectImageUpload.hospital),
                    selectinload(DirectImageUpload.lab_unit).selectinload(LabUnit.hospital),
                    selectinload(DirectImageUpload.camera),
                    selectinload(DirectImageUpload.disease),
                    selectinload(DirectImageUpload.area),
                )
            )
            
            # Apply lab unit access control for direct uploads
            if not is_admin_like and user_lab_unit_ids:
                direct_query = direct_query.filter(DirectImageUpload.lab_unit_id.in_(list(user_lab_unit_ids)))

            if hospital_id:
                direct_query = direct_query.filter(DirectImageUpload.hospital_id == hospital_id)
            # Only allow filtering by lab_unit_id if the user has access to that lab unit
            if lab_unit_id:
                if not is_admin_like and lab_unit_id not in user_lab_unit_ids:
                    from flask import abort
                    abort(403, description="Access denied to this lab unit")
                direct_query = direct_query.filter(DirectImageUpload.lab_unit_id == lab_unit_id)
            if camera_id:
                direct_query = direct_query.filter(DirectImageUpload.camera_id == camera_id)
            if disease_id:
                direct_query = direct_query.filter(DirectImageUpload.disease_id == disease_id)
            if area_id:
                direct_query = direct_query.filter(DirectImageUpload.area_id == area_id)
            if upload_start_dt:
                direct_query = direct_query.filter(DirectImageUpload.created_at >= upload_start_dt)
            if upload_end_dt:
                direct_query = direct_query.filter(DirectImageUpload.created_at <= upload_end_dt)
            if is_mydriatic is not None:
                direct_query = direct_query.filter(DirectImageUpload.is_mydriatic == is_mydriatic)

            direct_uploads = direct_query.all()

            for upload in direct_uploads:
                if has_encounter is True:
                    continue
                if has_dr_report is True:
                    continue
                if has_glaucoma_report is True:
                    continue

                hospital = upload.hospital
                lab_unit = upload.lab_unit
                camera = upload.camera
                disease = upload.disease
                area = upload.area

                created_at = _normalize_datetime(upload.created_at)

                records.append(
                    {
                        "uuid": upload.uuid,
                        "source": "direct",
                        "hospital_name": hospital.name if hospital else None,
                        "lab_unit_name": lab_unit.name if lab_unit else None,
                        "camera_name": camera.name if camera else None,
                        "disease_name": disease.name if disease else None,
                        "area_name": area.name if area else None,
                        "record_date": created_at,
                        "created_at": created_at,
                        "capture_date": None,
                        "encounter_id": None,
                        "has_dr": False,
                        "has_glaucoma": False,
                        "is_mydriatic": upload.is_mydriatic,
                        "view_url": url_for("analytics.view_upload", uuid_str=upload.uuid),
                    }
                )

        records.sort(key=lambda item: item.get("record_date") or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        total = len(records)
        start = (page - 1) * per_page
        end = start + per_page
        page_records = records[start:end]

        # Filter hospitals, lab units, etc. to only show those the user has access to
        if is_admin_like:
            hospitals = db.query(Hospital).order_by(Hospital.name).all()
            lab_units = db.query(LabUnit).order_by(LabUnit.name).all()
            cameras = db.query(Camera).order_by(Camera.name).all()
            diseases_all = db.query(Disease).order_by(Disease.name).all()
            areas = db.query(Area).order_by(Area.name).all()
        else:
            lab_units = (
                db.query(LabUnit)
                .filter(LabUnit.id.in_(list(user_lab_unit_ids)))
                .order_by(LabUnit.name)
                .all()
            )
            # Get hospitals for the allowed lab units
            hospital_ids = [lu.hospital_id for lu in lab_units]
            hospitals = (
                db.query(Hospital)
                .filter(Hospital.id.in_(hospital_ids))
                .order_by(Hospital.name)
                .all()
            )
            # For other filters, we'll still fetch them all but only show data from allowed lab units
            cameras = db.query(Camera).order_by(Camera.name).all()
            diseases_all = db.query(Disease).order_by(Disease.name).all()
            areas = db.query(Area).order_by(Area.name).all()

    finally:
        db.close()

    total_pages = max(1, (total + per_page - 1) // per_page) if total else 1

    filter_params = {
        "source": source,
        "hospital_id": hospital_id,
        "lab_unit_id": lab_unit_id,
        "camera_id": camera_id,
        "disease_id": disease_id,
        "area_id": area_id,
        "has_encounter": request.args.get("has_encounter", ""),
        "has_dr_report": request.args.get("has_dr_report", ""),
        "has_glaucoma_report": request.args.get("has_glaucoma_report", ""),
        "upload_start": request.args.get("upload_start", ""),
        "upload_end": request.args.get("upload_end", ""),
        "capture_start": request.args.get("capture_start", ""),
        "capture_end": request.args.get("capture_end", ""),
        "is_mydriatic": request.args.get("is_mydriatic", ""),
    }

    def _filter_kwargs(target_page: int) -> dict[str, Any]:
        params: dict[str, Any] = {"page": target_page}
        for key, value in filter_params.items():
            if value:
                params[key] = value
        return params

    prev_url = url_for("analytics.search_images", **_filter_kwargs(page - 1)) if page > 1 else None
    next_url = url_for("analytics.search_images", **_filter_kwargs(page + 1)) if page < total_pages else None

    return render_template(
        "analytics/search_images.html",
        rows=page_records,
        page=page,
        total=total,
        total_pages=total_pages,
        prev_url=prev_url,
        next_url=next_url,
        filters=filter_params,
        hospitals=hospitals,
        lab_units=lab_units,
        cameras=cameras,
        diseases=diseases_all,
        areas=areas,
    )