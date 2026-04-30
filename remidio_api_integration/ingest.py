"""Ingest staged Remidio metadata into EyeImageManager encounter/file rows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from auth.utils import utcnow
from models import (
    GradingTask,
    EncounterFile,
    EncounterFilePDF,
    IMAGE_DIR,
    PDF_DIR,
    PatientEncounters,
    RemidioExam,
    RemidioImage,
    RemidioReport,
    RemidioRoutingRule,
)
from utils.image_metadata import extract_image_metadata, upsert_image_metadata
from utils.image_processing import generate_thumbnail, get_thumbnail_filename, strip_exif_data
from utils.log_sanitize import sanitize_log_value

from .client import RemidioClient
from .errors import RemidioConfigError, RemidioRemoteError


MAX_FILE_BYTES = 100 * 1024 * 1024


@dataclass
class IngestSummary:
    exams_seen: int = 0
    encounters_created: int = 0
    encounters_reused: int = 0
    images_seen: int = 0
    images_downloaded: int = 0
    images_skipped: int = 0
    reports_seen: int = 0
    reports_downloaded: int = 0
    reports_skipped: int = 0
    tasks_created: int = 0
    tasks_reused: int = 0
    route_errors: int = 0
    download_errors: int = 0

    def as_dict(self) -> dict[str, int]:
        return self.__dict__.copy()


def ingest_staged_files(
    db: Session,
    *,
    connection_id: int,
    client: RemidioClient,
    payload: dict[str, Any],
) -> dict[str, Any]:
    include_images = _bool(payload.get("include_images"), default=True)
    include_reports = _bool(payload.get("include_reports"), default=True)
    create_tasks = _bool(payload.get("create_tasks"), default=True)
    dry_run = _bool(payload.get("dry_run"), default=False)
    limit = min(max(_optional_int(payload.get("limit")) or 20, 1), 200)

    exams = _select_exams(db, connection_id=connection_id, payload=payload, limit=limit)
    summary = IngestSummary(exams_seen=len(exams))
    details: list[dict[str, Any]] = []

    for exam in exams:
        exam_detail = _ingest_exam(
            db,
            client=client,
            exam=exam,
            include_images=include_images,
            include_reports=include_reports,
            create_tasks=create_tasks,
            dry_run=dry_run,
            summary=summary,
        )
        details.append(exam_detail)

    return {
        "connection_id": connection_id,
        "dry_run": dry_run,
        "limit": limit,
        "summary": summary.as_dict(),
        "exams": details,
    }


def _select_exams(db: Session, *, connection_id: int, payload: dict[str, Any], limit: int) -> list[RemidioExam]:
    query = (
        db.query(RemidioExam)
        .options(
            selectinload(RemidioExam.images),
            selectinload(RemidioExam.reports),
            selectinload(RemidioExam.site),
        )
        .filter(RemidioExam.remidio_connection_id == connection_id)
    )

    local_exam_ids = payload.get("remidio_exam_row_ids")
    if isinstance(local_exam_ids, list) and local_exam_ids:
        query = query.filter(RemidioExam.id.in_([int(value) for value in local_exam_ids]))

    external_exam_ids = payload.get("remidio_exam_ids")
    if isinstance(external_exam_ids, list) and external_exam_ids:
        query = query.filter(RemidioExam.remidio_exam_id.in_([str(value) for value in external_exam_ids]))

    site_custom_identifier = payload.get("site_custom_identifier")
    if site_custom_identifier:
        query = query.filter(RemidioExam.site_custom_identifier == str(site_custom_identifier).strip())

    start_dt = _optional_date_boundary(payload.get("start_date"), end=False)
    end_dt = _optional_date_boundary(payload.get("end_date"), end=True)
    if start_dt is not None:
        query = query.filter(RemidioExam.exam_date >= start_dt)
    if end_dt is not None:
        query = query.filter(RemidioExam.exam_date <= end_dt)

    pending_only = _bool(payload.get("pending_only"), default=True)
    if pending_only:
        query = query.filter(
            (RemidioExam.patient_encounter_id.is_(None))
            | RemidioExam.images.any(RemidioImage.encounter_file_id.is_(None))
            | RemidioExam.reports.any(RemidioReport.encounter_file_pdf_id.is_(None))
        )

    return query.order_by(RemidioExam.exam_date.asc().nullslast(), RemidioExam.id.asc()).limit(limit).all()


def _ingest_exam(
    db: Session,
    *,
    client: RemidioClient,
    exam: RemidioExam,
    include_images: bool,
    include_reports: bool,
    create_tasks: bool,
    dry_run: bool,
    summary: IngestSummary,
) -> dict[str, Any]:
    detail = {
        "remidio_exam_row_id": exam.id,
        "remidio_exam_id": exam.remidio_exam_id,
        "patient_encounter_id": exam.patient_encounter_id,
        "images": [],
        "reports": [],
    }

    route_cache: dict[str, RemidioRoutingRule | None] = {}
    encounter = db.get(PatientEncounters, exam.patient_encounter_id) if exam.patient_encounter_id else None
    if encounter is not None:
        summary.encounters_reused += 1

    if include_images:
        for image in exam.images:
            summary.images_seen += 1
            image_result = _ingest_image(
                db,
                client=client,
                exam=exam,
                image=image,
                encounter=encounter,
                route_cache=route_cache,
                create_tasks=create_tasks,
                dry_run=dry_run,
                summary=summary,
            )
            if encounter is None and image_result.get("patient_encounter_id") and not dry_run:
                encounter = db.get(PatientEncounters, image_result["patient_encounter_id"])
                exam.patient_encounter_id = encounter.id if encounter else None
                detail["patient_encounter_id"] = exam.patient_encounter_id
                summary.encounters_created += 1
            detail["images"].append(image_result)

    if include_reports:
        for report in exam.reports:
            summary.reports_seen += 1
            report_result = _ingest_report(
                db,
                client=client,
                exam=exam,
                report=report,
                encounter=encounter,
                route_cache=route_cache,
                dry_run=dry_run,
                summary=summary,
            )
            if encounter is None and report_result.get("patient_encounter_id") and not dry_run:
                encounter = db.get(PatientEncounters, report_result["patient_encounter_id"])
                exam.patient_encounter_id = encounter.id if encounter else None
                detail["patient_encounter_id"] = exam.patient_encounter_id
                summary.encounters_created += 1
            detail["reports"].append(report_result)

    return detail


def _ingest_image(
    db: Session,
    *,
    client: RemidioClient,
    exam: RemidioExam,
    image: RemidioImage,
    encounter: PatientEncounters | None,
    route_cache: dict[str, RemidioRoutingRule | None],
    create_tasks: bool,
    dry_run: bool,
    summary: IngestSummary,
) -> dict[str, Any]:
    if image.encounter_file_id:
        summary.images_skipped += 1
        return {"remidio_image_id": image.remidio_image_id, "status": "already_ingested", "encounter_file_id": image.encounter_file_id}

    rule = _resolve_rule(db, exam=exam, device_type=image.device_type, route_cache=route_cache)
    if rule is None:
        summary.route_errors += 1
        summary.images_skipped += 1
        image.download_error = "No active unique routing rule for Remidio site/device."
        return {"remidio_image_id": image.remidio_image_id, "status": "no_route"}

    if encounter is not None and (encounter.project_id != rule.project_id or encounter.lab_unit_id != rule.lab_unit_id):
        summary.route_errors += 1
        summary.images_skipped += 1
        image.download_error = "Image route conflicts with the existing encounter route."
        return {"remidio_image_id": image.remidio_image_id, "status": "route_conflict"}

    if dry_run:
        return {"remidio_image_id": image.remidio_image_id, "status": "would_download", "project_id": rule.project_id, "lab_unit_id": rule.lab_unit_id}

    encounter = encounter or _create_encounter(db, exam, rule)
    try:
        content, content_type = client.download_file(_source_url(image), max_bytes=MAX_FILE_BYTES)
        extension = _image_extension(content, content_type, image.remidio_path)
        safe_content = _strip_image_exif(content)
        filename = f"{uuid4()}{extension}"
        target_path = _dated_dir(IMAGE_DIR, exam) / filename
        target_path.write_bytes(safe_content)
        thumbnail_filename = _generate_thumbnail(target_path, filename)
        encounter_file = EncounterFile(
            patient_encounter_id=encounter.id,
            filename=filename,
            file_type="image",
            uuid=str(uuid4()),
            eye_side=_normalize_eye_side(image.laterality),
            lab_unit_id=rule.lab_unit_id,
            camera_id=rule.camera_id,
            project_id=rule.project_id,
            hospital_id=rule.lab_unit.hospital_id if rule.lab_unit else None,
            thumbnail_filename=thumbnail_filename,
        )
        db.add(encounter_file)
        db.flush()
        _store_image_metadata(db, encounter_file, content=safe_content)

        image.encounter_file_id = encounter_file.id
        image.downloaded_at = utcnow()
        image.download_error = None
        db.flush()
        summary.images_downloaded += 1

        if create_tasks and rule.default_disease_id is not None:
            created = _create_task_if_missing(db, encounter_file.id, rule.default_disease_id, rule.lab_unit_id)
            if created:
                summary.tasks_created += 1
            else:
                summary.tasks_reused += 1

        return {
            "remidio_image_id": image.remidio_image_id,
            "status": "downloaded",
            "patient_encounter_id": encounter.id,
            "encounter_file_id": encounter_file.id,
            "filename": filename,
        }
    except Exception as exc:
        summary.download_errors += 1
        summary.images_skipped += 1
        image.download_error = str(sanitize_log_value(exc))[:1000]
        return {"remidio_image_id": image.remidio_image_id, "status": "download_error", "error": image.download_error}


def _ingest_report(
    db: Session,
    *,
    client: RemidioClient,
    exam: RemidioExam,
    report: RemidioReport,
    encounter: PatientEncounters | None,
    route_cache: dict[str, RemidioRoutingRule | None],
    dry_run: bool,
    summary: IngestSummary,
) -> dict[str, Any]:
    if report.encounter_file_pdf_id:
        summary.reports_skipped += 1
        return {"remidio_report_id": report.remidio_report_id, "status": "already_ingested", "encounter_file_pdf_id": report.encounter_file_pdf_id}

    rule = _resolve_report_rule(db, exam=exam, route_cache=route_cache)
    if rule is None:
        summary.route_errors += 1
        summary.reports_skipped += 1
        report.download_error = "No active unique routing rule for Remidio report."
        return {"remidio_report_id": report.remidio_report_id, "status": "no_route"}

    if encounter is not None and (encounter.project_id != rule.project_id or encounter.lab_unit_id != rule.lab_unit_id):
        summary.route_errors += 1
        summary.reports_skipped += 1
        report.download_error = "Report route conflicts with the existing encounter route."
        return {"remidio_report_id": report.remidio_report_id, "status": "route_conflict"}

    if dry_run:
        return {"remidio_report_id": report.remidio_report_id, "status": "would_download", "project_id": rule.project_id, "lab_unit_id": rule.lab_unit_id}

    encounter = encounter or _create_encounter(db, exam, rule)
    try:
        content, content_type = client.download_file(_source_url(report), max_bytes=MAX_FILE_BYTES)
        if not _looks_like_pdf(content, content_type, report.remidio_path):
            raise RemidioRemoteError("Downloaded Remidio report is not a PDF.")
        filename = f"{uuid4()}.pdf"
        target_path = _dated_dir(PDF_DIR, exam) / filename
        target_path.write_bytes(content)
        pdf = EncounterFilePDF(
            patient_encounter_id=encounter.id,
            filename=filename,
            file_type="pdf",
            uuid=str(uuid4()),
            lab_unit_id=rule.lab_unit_id,
            project_id=rule.project_id,
            hospital_id=rule.lab_unit.hospital_id if rule.lab_unit else None,
        )
        db.add(pdf)
        db.flush()

        report.encounter_file_pdf_id = pdf.id
        report.downloaded_at = utcnow()
        report.download_error = None
        db.flush()
        summary.reports_downloaded += 1
        return {
            "remidio_report_id": report.remidio_report_id,
            "status": "downloaded",
            "patient_encounter_id": encounter.id,
            "encounter_file_pdf_id": pdf.id,
            "filename": filename,
        }
    except Exception as exc:
        summary.download_errors += 1
        summary.reports_skipped += 1
        report.download_error = str(sanitize_log_value(exc))[:1000]
        return {"remidio_report_id": report.remidio_report_id, "status": "download_error", "error": report.download_error}


def _resolve_rule(
    db: Session,
    *,
    exam: RemidioExam,
    device_type: str | None,
    route_cache: dict[str, RemidioRoutingRule | None],
) -> RemidioRoutingRule | None:
    normalized_device = (device_type or "").strip().upper()
    site_identifier = _site_identifier(exam)
    if not site_identifier or not normalized_device:
        return None
    cache_key = f"{site_identifier}:{normalized_device}"
    if cache_key in route_cache:
        return route_cache[cache_key]
    rules = (
        db.query(RemidioRoutingRule)
        .options(selectinload(RemidioRoutingRule.lab_unit))
        .filter(
            RemidioRoutingRule.remidio_connection_id == exam.remidio_connection_id,
            RemidioRoutingRule.site_custom_identifier == site_identifier,
            RemidioRoutingRule.remidio_device_type == normalized_device,
            RemidioRoutingRule.active.is_(True),
        )
        .all()
    )
    route_cache[cache_key] = rules[0] if len(rules) == 1 else None
    return route_cache[cache_key]


def _resolve_report_rule(db: Session, *, exam: RemidioExam, route_cache: dict[str, RemidioRoutingRule | None]) -> RemidioRoutingRule | None:
    for device_type in exam.device_types or []:
        rule = _resolve_rule(db, exam=exam, device_type=device_type, route_cache=route_cache)
        if rule is not None:
            return rule
    return None


def _create_encounter(db: Session, exam: RemidioExam, rule: RemidioRoutingRule) -> PatientEncounters:
    encounter = PatientEncounters(
        uuid=str(uuid4()),
        is_set_based=False,
        name=_encounter_patient_name(exam),
        patient_id=exam.remidio_patient_mrn or exam.remidio_patient_id or f"remidio-{exam.remidio_exam_id}",
        capture_date=_capture_date_string(exam),
        capture_date_dt=_capture_date(exam),
        lab_unit_id=rule.lab_unit_id,
        project_id=rule.project_id,
        disease_id=rule.default_disease_id,
    )
    db.add(encounter)
    db.flush()
    exam.patient_encounter_id = encounter.id
    return encounter


def _create_task_if_missing(db: Session, encounter_file_id: int, disease_id: int, lab_unit_id: int) -> bool:
    existing = db.execute(
        select(GradingTask).where(
            GradingTask.encounter_file_id == encounter_file_id,
            GradingTask.disease_id == disease_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return False
    db.add(
        GradingTask(
            encounter_file_id=encounter_file_id,
            disease_id=disease_id,
            lab_unit_id=lab_unit_id,
            state="pending",
        )
    )
    db.flush()
    return True


def _source_url(row: RemidioImage | RemidioReport) -> str:
    value = row.remidio_path
    if value:
        return value
    raw = row.raw_json or {}
    if isinstance(raw, dict):
        for key in ("downloadUrl", "downloadURL", "url", "path"):
            candidate = raw.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
    raise RemidioConfigError("Remidio file row has no download URL.")


def _site_identifier(exam: RemidioExam) -> str | None:
    if exam.site_custom_identifier:
        return exam.site_custom_identifier
    if exam.site and exam.site.site_custom_identifier:
        return exam.site.site_custom_identifier
    return None


def _dated_dir(root: Path, exam: RemidioExam) -> Path:
    dt = exam.exam_date or utcnow()
    date_str = dt.strftime("%Y_%m_%d")
    path = root / date_str
    path.mkdir(parents=True, exist_ok=True)
    return path


def _image_extension(content: bytes, content_type: str | None, path: str | None) -> str:
    content_type = (content_type or "").lower().split(";")[0].strip()
    if content_type in {"image/jpeg", "image/jpg"}:
        return ".jpg"
    if content_type == "image/png":
        return ".png"
    if content_type == "image/webp":
        return ".webp"
    if content_type == "image/bmp":
        return ".bmp"
    suffix = Path((path or "").split("?", 1)[0]).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}:
        return ".jpg" if suffix == ".jpeg" else suffix
    try:
        from io import BytesIO

        with Image.open(BytesIO(content)) as image:
            fmt = (image.format or "").lower()
        if fmt in {"jpeg", "jpg"}:
            return ".jpg"
        if fmt in {"png", "webp", "bmp"}:
            return f".{fmt}"
    except UnidentifiedImageError as exc:
        raise RemidioRemoteError("Downloaded Remidio image is not a valid image.") from exc
    return ".jpg"


def _strip_image_exif(content: bytes) -> bytes:
    try:
        return strip_exif_data(content)
    except Exception:
        return content


def _generate_thumbnail(image_path: Path, filename: str) -> str | None:
    try:
        thumbnail_filename = get_thumbnail_filename(filename)
        if generate_thumbnail(image_path, image_path.parent / thumbnail_filename):
            return thumbnail_filename
    except Exception:
        return None
    return None


def _store_image_metadata(db: Session, encounter_file: EncounterFile, *, content: bytes) -> None:
    try:
        metadata = extract_image_metadata(image_bytes=content, file_size_bytes=len(content))
        upsert_image_metadata(
            db,
            image_uuid=str(encounter_file.uuid),
            image_variant="orig",
            encounter_file_id=encounter_file.id,
            metadata=metadata,
        )
    except Exception:
        return


def _looks_like_pdf(content: bytes, content_type: str | None, path: str | None) -> bool:
    content_type = (content_type or "").lower().split(";")[0].strip()
    if content.startswith(b"%PDF"):
        return True
    if content_type == "application/pdf":
        return True
    return Path((path or "").split("?", 1)[0]).suffix.lower() == ".pdf"


def _normalize_eye_side(value: str | None) -> str | None:
    normalized = (value or "").strip().upper()
    if normalized in {"RIGHT", "R", "OD"}:
        return "right"
    if normalized in {"LEFT", "L", "OS"}:
        return "left"
    return None


def _capture_date(exam: RemidioExam) -> date | None:
    if exam.exam_date is None:
        return None
    return exam.exam_date.date()


def _capture_date_string(exam: RemidioExam) -> str:
    if exam.exam_date is None:
        return ""
    return exam.exam_date.date().isoformat()


def _encounter_patient_name(exam: RemidioExam) -> str:
    identifier = exam.remidio_patient_id or exam.remidio_patient_mrn or exam.remidio_exam_id
    return f"Remidio Patient {identifier}"


def _optional_date_boundary(value: Any, *, end: bool) -> datetime | None:
    if value in {None, ""}:
        return None
    normalized = str(value).strip()
    parsed_date: date | None = None
    for fmt in ("%Y-%m-%d", "%d-%m-%Y"):
        try:
            parsed_date = datetime.strptime(normalized, fmt).date()
            break
        except ValueError:
            continue
    if parsed_date is None:
        raise RemidioConfigError("start_date/end_date must be YYYY-MM-DD or DD-MM-YYYY.")
    boundary_time = time.max if end else time.min
    return datetime.combine(parsed_date, boundary_time, tzinfo=timezone.utc)


def _optional_int(value: Any) -> int | None:
    if value in {None, ""}:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise RemidioConfigError("Expected an integer value.")


def _bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)
