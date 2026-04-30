from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List

from flask import current_app, jsonify
from flask_login import current_user
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from sqlalchemy import func, case

from api import api_bp
from app_cache import cache
from auth.roles import roles_required
from models import (
    Job,
    JobItem,
    LabUnit,
    ZipFile,
    PatientEncounters,
    EncounterFile,
    DiabeticRetinopathyReport,
    GlaucomaReport,
    DirectImageUpload,
    Disease,
)
from utils.log_sanitize import sanitize_log_value
from utils.utils import with_session

_UPLOAD_TYPES = {
    "zip": "zip upload",
    "direct": "direct image",
    "pregraded": "pregraded",
}


def _resolve_user_timezone() -> ZoneInfo:
    tz_name = getattr(current_user, "timezone", None)
    if not tz_name:
        tz_name = (
            current_app.config.get("DEFAULT_DISPLAY_TIMEZONE")
            or current_app.config.get("TIMEZONE")
        )

    if not tz_name:
        tz_name = "UTC"

    try:
        return ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        current_app.logger.warning(
            "Unknown timezone '%s', falling back to UTC",
            sanitize_log_value(tz_name),
        )
        return ZoneInfo("UTC")


def _day_bounds_utc(day: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    start_local = datetime.combine(day, time.min).replace(tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def _cache_key(prefix: str, include_day: bool = False) -> str:
    user_id = getattr(current_user, "id", None)
    hospital_id = getattr(current_user, "hospital_id", None)
    tz_name = getattr(current_user, "timezone", None) or "UTC"
    parts = [prefix, f"u:{user_id}", f"h:{hospital_id}", f"tz:{tz_name}"]
    if include_day:
        day = datetime.now(_resolve_user_timezone()).date().isoformat()
        parts.append(f"d:{day}")
    return ":".join(parts)


def _get_hospital_lab_units(db) -> List[int]:
    hospital_id = getattr(current_user, "hospital_id", None)
    if not hospital_id:
        return []
    lab_units = db.query(LabUnit.id).filter(LabUnit.hospital_id == hospital_id).all()
    return [lu_id for (lu_id,) in lab_units]


def _count_jobs(db, upload_type: str, lab_unit_ids: List[int], start: datetime | None = None, end: datetime | None = None, mine: bool = False) -> int:
    query = db.query(func.count(Job.id)).filter(Job.upload_type == upload_type)
    if lab_unit_ids:
        query = query.filter(Job.lab_unit_id.in_(lab_unit_ids))
    else:
        return 0

    if start is not None:
        query = query.filter(Job.created_at >= start)
    if end is not None:
        query = query.filter(Job.created_at < end)
    if mine:
        query = query.filter(Job.uploader_user_id == current_user.id)

    return int(query.scalar() or 0)


def _build_matrix_counts(db, lab_unit_ids: List[int], start: datetime | None, end: datetime | None) -> Dict[str, Dict[str, Dict[str, int]]]:
    matrix: Dict[str, Dict[str, Dict[str, int]]] = {
        "mine": {"today": {}, "cumulative": {}},
        "total": {"today": {}, "cumulative": {}},
    }

    for key, upload_type in _UPLOAD_TYPES.items():
        matrix["mine"]["today"][key] = _count_jobs(db, upload_type, lab_unit_ids, start=start, end=end, mine=True)
        matrix["mine"]["cumulative"][key] = _count_jobs(db, upload_type, lab_unit_ids, mine=True)
        matrix["total"]["today"][key] = _count_jobs(db, upload_type, lab_unit_ids, start=start, end=end, mine=False)
        matrix["total"]["cumulative"][key] = _count_jobs(db, upload_type, lab_unit_ids, mine=False)

    return matrix


def _zip_day_metrics(
    db,
    lab_unit_ids: List[int],
    start: datetime,
    end: datetime,
    uploader_id: int | None = None,
) -> Dict[str, Any]:
    if not lab_unit_ids:
        return {
            "attempted": 0,
            "success": 0,
            "images_processed": 0,
            "dr_pdfs": 0,
            "glaucoma_pdfs": 0,
            "no_ai_reports": 0,
            "encounter_capture_date_min": None,
            "encounter_capture_date_max": None,
        }

    job_filter = [
        Job.upload_type == _UPLOAD_TYPES["zip"],
        Job.created_at >= start,
        Job.created_at < end,
        Job.lab_unit_id.in_(lab_unit_ids),
    ]
    if uploader_id:
        job_filter.append(Job.uploader_user_id == uploader_id)

    attempted = (
        db.query(func.count(JobItem.id))
        .join(Job, Job.id == JobItem.job_id)
        .filter(*job_filter)
        .scalar()
    ) or 0

    success = (
        db.query(func.count(JobItem.id))
        .join(Job, Job.id == JobItem.job_id)
        .filter(*job_filter)
        .filter(JobItem.state.in_(["completed", "ok"]))
        .scalar()
    ) or 0

    base_zip_join = (
        db.query(ZipFile.id)
        .join(JobItem, ZipFile.zip_filename == JobItem.filename)
        .join(Job, Job.id == JobItem.job_id)
        .filter(*job_filter)
        .filter(JobItem.state.in_(["completed", "ok"]))
        .subquery()
    )

    encounter_filter = [
        PatientEncounters.zip_file_id == base_zip_join.c.id,
        PatientEncounters.lab_unit_id.in_(lab_unit_ids),
    ]

    images_processed = (
        db.query(func.count(EncounterFile.id))
        .join(PatientEncounters, PatientEncounters.id == EncounterFile.patient_encounter_id)
        .filter(*encounter_filter)
        .scalar()
    ) or 0

    dr_pdfs = (
        db.query(func.count(DiabeticRetinopathyReport.id))
        .join(PatientEncounters, PatientEncounters.id == DiabeticRetinopathyReport.patient_encounter_id)
        .filter(*encounter_filter)
        .scalar()
    ) or 0

    glaucoma_pdfs = (
        db.query(func.count(GlaucomaReport.id))
        .join(PatientEncounters, PatientEncounters.id == GlaucomaReport.patient_encounter_id)
        .filter(*encounter_filter)
        .scalar()
    ) or 0

    no_ai_reports = (
        db.query(func.count(PatientEncounters.id))
        .filter(*encounter_filter)
        .filter(~db.query(DiabeticRetinopathyReport.id).filter(DiabeticRetinopathyReport.patient_encounter_id == PatientEncounters.id).exists())
        .filter(~db.query(GlaucomaReport.id).filter(GlaucomaReport.patient_encounter_id == PatientEncounters.id).exists())
        .scalar()
    ) or 0

    capture_min_max = (
        db.query(
            func.min(PatientEncounters.capture_date_dt),
            func.max(PatientEncounters.capture_date_dt),
        )
        .filter(*encounter_filter)
        .first()
    )

    return {
        "attempted": int(attempted),
        "success": int(success),
        "images_processed": int(images_processed),
        "dr_pdfs": int(dr_pdfs),
        "glaucoma_pdfs": int(glaucoma_pdfs),
        "no_ai_reports": int(no_ai_reports),
        "encounter_capture_date_min": capture_min_max[0].isoformat() if capture_min_max and capture_min_max[0] else None,
        "encounter_capture_date_max": capture_min_max[1].isoformat() if capture_min_max and capture_min_max[1] else None,
    }


def _build_zip_daily_metrics(
    db,
    lab_unit_ids: List[int],
    days: int,
    uploader_id: int | None = None,
) -> List[Dict[str, Any]]:
    tz = _resolve_user_timezone()
    today_local = datetime.now(tz).date()
    metrics: List[Dict[str, Any]] = []

    for offset in range(days):
        day = today_local - timedelta(days=offset)
        start, end = _day_bounds_utc(day, tz)
        day_stats = _zip_day_metrics(db, lab_unit_ids, start, end, uploader_id=uploader_id)
        day_stats["date"] = day.isoformat()
        metrics.append(day_stats)

    return list(reversed(metrics))

def _direct_pregraded_by_disease(
    db,
    lab_unit_ids: List[int],
    start: datetime,
    end: datetime,
    uploader_id: int | None = None,
) -> List[Dict[str, Any]]:
    hospital_id = getattr(current_user, "hospital_id", None)
    if not hospital_id:
        return []

    query = (
        db.query(
            Disease.id.label("disease_id"),
            Disease.name.label("disease_name"),
            func.sum(case((DirectImageUpload.is_pregraded.is_(False), 1), else_=0)).label("direct_count"),
            func.sum(case((DirectImageUpload.is_pregraded.is_(True), 1), else_=0)).label("pregraded_count"),
        )
        .join(Disease, Disease.id == DirectImageUpload.disease_id)
        .filter(DirectImageUpload.hospital_id == hospital_id)
        .filter(DirectImageUpload.created_at >= start, DirectImageUpload.created_at < end)
    )

    if lab_unit_ids:
        query = query.filter(DirectImageUpload.lab_unit_id.in_(lab_unit_ids))
    if uploader_id:
        query = query.filter(DirectImageUpload.uploader_id == uploader_id)

    rows = query.group_by(Disease.id, Disease.name).order_by(Disease.name).all()
    return [
        {
            "disease_id": int(row.disease_id),
            "disease_name": row.disease_name,
            "direct_count": int(row.direct_count or 0),
            "pregraded_count": int(row.pregraded_count or 0),
        }
        for row in rows
    ]


@api_bp.route("/upload-stats/today", methods=["GET"])
@roles_required("admin", "local_admin", "data_manager", "ophthalmologist", "resident", "optometrist", "fileUploader")
@cache.cached(timeout=120, key_prefix=lambda: _cache_key("upload-stats:today", include_day=True))
def upload_stats_today():
    tz = _resolve_user_timezone()
    today_local = datetime.now(tz).date()
    start, end = _day_bounds_utc(today_local, tz)
    with with_session() as db:
        lab_unit_ids = _get_hospital_lab_units(db)
        data = {
            "timezone": tz.key,
            "matrix": _build_matrix_counts(db, lab_unit_ids, start=start, end=end),
            "zip_daily": {
                "my": _build_zip_daily_metrics(db, lab_unit_ids, days=1, uploader_id=current_user.id),
                "all": _build_zip_daily_metrics(db, lab_unit_ids, days=1),
            },
            "direct_pregraded_by_disease": {
                "range": "today",
                "my": _direct_pregraded_by_disease(db, lab_unit_ids, start=start, end=end, uploader_id=current_user.id),
                "all": _direct_pregraded_by_disease(db, lab_unit_ids, start=start, end=end),
            },
        }

    return jsonify({
        "success": True,
        "data": data,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


@api_bp.route("/upload-stats/last-7-days", methods=["GET"])
@roles_required("admin", "local_admin", "data_manager", "ophthalmologist", "resident", "optometrist", "fileUploader")
@cache.cached(timeout=20 * 60 * 60, key_prefix=lambda: _cache_key("upload-stats:last-7-days", include_day=True))
def upload_stats_last_7_days():
    tz = _resolve_user_timezone()
    today_local = datetime.now(tz).date()
    start, end = _day_bounds_utc(today_local, tz)
    with with_session() as db:
        lab_unit_ids = _get_hospital_lab_units(db)
        data = {
            "timezone": tz.key,
            "matrix": _build_matrix_counts(db, lab_unit_ids, start=start, end=end),
            "zip_daily": {
                "my": _build_zip_daily_metrics(db, lab_unit_ids, days=7, uploader_id=current_user.id),
                "all": _build_zip_daily_metrics(db, lab_unit_ids, days=7),
            },
            "direct_pregraded_by_disease": {
                "range": "last_7_days",
                "my": _direct_pregraded_by_disease(db, lab_unit_ids, start=start - timedelta(days=6), end=end, uploader_id=current_user.id),
                "all": _direct_pregraded_by_disease(db, lab_unit_ids, start=start - timedelta(days=6), end=end),
            },
        }

    return jsonify({
        "success": True,
        "data": data,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
