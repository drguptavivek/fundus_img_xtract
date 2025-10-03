"""Routes for the results blueprint."""

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

TASK_STATE_OPTIONS: tuple[str, ...] = (
    "pending",
    "resident_done",
    "faculty_done",
    "arbitration",
    "final",
)


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

            if hospital_id:
                encounter_query = encounter_query.filter(Hospital.id == hospital_id)
            if lab_unit_id:
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

            if hospital_id:
                direct_query = direct_query.filter(DirectImageUpload.hospital_id == hospital_id)
            if lab_unit_id:
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

        hospitals = db.query(Hospital).order_by(Hospital.name).all()
        lab_units = db.query(LabUnit).order_by(LabUnit.name).all()
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
