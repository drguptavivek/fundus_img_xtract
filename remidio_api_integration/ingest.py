"""Ingest staged Remidio metadata into EyeImageManager encounter/file rows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
import logging
from pathlib import Path
from typing import Any
from uuid import uuid4

from PIL import Image, UnidentifiedImageError
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session, selectinload

from auth.utils import utcnow
from models import (
    BASE_DIR,
    EncounterSetAttachment,
    EncounterSetImage,
    PatientEncounters,
    RemidioExam,
    RemidioImage,
    RemidioReport,
)
from upload_profiles.models import PatientEncounterTargetDisease
from utils.image_processing import generate_thumbnail, get_thumbnail_filename, strip_exif_data
from utils.log_sanitize import sanitize_log_value

from .client import RemidioClient
from .errors import RemidioConfigError, RemidioIntegrationError, RemidioRemoteError
from .mapper import map_exam_payload
from .models import ProjectUploadProfileRemidioApiBinding, RemidioApiExamEncounter
from .routing import resolve_binding_for_image


MAX_FILE_BYTES = 100 * 1024 * 1024
logger = logging.getLogger(__name__)


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
            | RemidioExam.images.any(
                and_(
                    RemidioImage.encounter_file_id.is_(None),
                    RemidioImage.encounter_set_image_id.is_(None),
                )
            )
            | RemidioExam.reports.any(
                and_(
                    RemidioReport.encounter_file_pdf_id.is_(None),
                    RemidioReport.encounter_set_attachment_id.is_(None),
                )
            )
        )

    return query.order_by(RemidioExam.exam_date.asc().nullslast(), RemidioExam.id.asc()).limit(limit).all()


def _ingest_exam(
    db: Session,
    *,
    client: RemidioClient,
    exam: RemidioExam,
    include_images: bool,
    include_reports: bool,
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

    mapped_metadata = map_exam_payload(exam.raw_json or {}, site_custom_identifier=_site_identifier(exam))
    encounters_by_binding: dict[int, PatientEncounters] = {}

    if include_images:
        for image in exam.images:
            summary.images_seen += 1
            image_result = _ingest_image(
                db,
                client=client,
                exam=exam,
                image=image,
                mapped_metadata=mapped_metadata,
                encounters_by_binding=encounters_by_binding,
                dry_run=dry_run,
                summary=summary,
            )
            if image_result.get("patient_encounter_id") and not detail["patient_encounter_id"]:
                detail["patient_encounter_id"] = image_result["patient_encounter_id"]
            detail["images"].append(image_result)

    if include_reports:
        for report in exam.reports:
            summary.reports_seen += 1
            report_result = _ingest_report(
                db,
                client=client,
                exam=exam,
                report=report,
                mapped_metadata=mapped_metadata,
                encounters_by_binding=encounters_by_binding,
                dry_run=dry_run,
                summary=summary,
            )
            if report_result.get("patient_encounter_id") and not detail["patient_encounter_id"]:
                detail["patient_encounter_id"] = report_result["patient_encounter_id"]
            detail["reports"].append(report_result)

    return detail


def _ingest_image(
    db: Session,
    *,
    client: RemidioClient,
    exam: RemidioExam,
    image: RemidioImage,
    mapped_metadata,
    encounters_by_binding: dict[int, PatientEncounters],
    dry_run: bool,
    summary: IngestSummary,
) -> dict[str, Any]:
    if image.encounter_set_image_id:
        summary.images_skipped += 1
        return {"remidio_image_id": image.remidio_image_id, "status": "already_ingested", "encounter_set_image_id": image.encounter_set_image_id}
    if image.encounter_file_id:
        summary.images_skipped += 1
        return {"remidio_image_id": image.remidio_image_id, "status": "already_ingested", "encounter_file_id": image.encounter_file_id}

    binding = resolve_binding_for_image(db, exam=exam, device_type=image.device_type)
    if binding is None:
        summary.route_errors += 1
        summary.images_skipped += 1
        image.download_error = "No active unique Remidio API project binding for site/device/date."
        return {"remidio_image_id": image.remidio_image_id, "status": "no_route"}

    if dry_run:
        project_profile = binding.project_profile
        return {
            "remidio_image_id": image.remidio_image_id,
            "status": "would_download",
            "project_id": project_profile.project_id,
            "upload_profile_id": project_profile.upload_profile_id,
            "lab_unit_id": binding.lab_unit_id,
        }

    encounter = _encounter_for_binding(db, exam, binding, mapped_metadata, encounters_by_binding, summary)
    try:
        content, content_type = client.download_file(_source_url(image), max_bytes=MAX_FILE_BYTES)
        extension = _image_extension(content, content_type, image.remidio_path)
        safe_content = _strip_image_exif(content)
        filename = f"{uuid4()}{extension}"
        folder_rel = _encounter_set_folder_rel(encounter)
        target_path = BASE_DIR / folder_rel / filename
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(safe_content)
        thumbnail_filename = _generate_encounter_set_thumbnail(target_path, filename)
        image_metadata = _image_metadata(mapped_metadata, image.remidio_image_id)
        set_image = EncounterSetImage(
            uuid=str(uuid4()),
            patient_encounter_id=encounter.id,
            spatial_position=_next_spatial_position(db, encounter.id),
            original_filename=filename,
            folder_rel=folder_rel,
            asset_kind="clinical_image",
            creates_task=True,
            is_pii=False,
            visible_to_grader=True,
            project_id=encounter.project_id,
            camera_id=binding.camera_id,
            hospital_id=binding.lab_unit.hospital_id if binding.lab_unit else None,
            thumbnail_filename=thumbnail_filename,
            metadata_json=image_metadata,
        )
        db.add(set_image)
        db.flush()

        image.encounter_set_image_id = set_image.id
        image.downloaded_at = utcnow()
        image.download_error = None
        db.flush()
        summary.images_downloaded += 1

        return {
            "remidio_image_id": image.remidio_image_id,
            "status": "downloaded",
            "patient_encounter_id": encounter.id,
            "encounter_set_image_id": set_image.id,
            "filename": filename,
        }
    except (OSError, RemidioIntegrationError, UnidentifiedImageError) as exc:
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
    mapped_metadata,
    encounters_by_binding: dict[int, PatientEncounters],
    dry_run: bool,
    summary: IngestSummary,
) -> dict[str, Any]:
    if report.encounter_set_attachment_id:
        summary.reports_skipped += 1
        return {"remidio_report_id": report.remidio_report_id, "status": "already_ingested", "encounter_set_attachment_id": report.encounter_set_attachment_id}
    if report.encounter_file_pdf_id:
        summary.reports_skipped += 1
        return {"remidio_report_id": report.remidio_report_id, "status": "already_ingested", "encounter_file_pdf_id": report.encounter_file_pdf_id}

    binding = _resolve_report_binding(db, exam=exam, report=report)
    if binding is None:
        summary.route_errors += 1
        summary.reports_skipped += 1
        report.download_error = "No active unique Remidio API project binding for report."
        return {"remidio_report_id": report.remidio_report_id, "status": "no_route"}

    if dry_run:
        project_profile = binding.project_profile
        return {
            "remidio_report_id": report.remidio_report_id,
            "status": "would_download",
            "project_id": project_profile.project_id,
            "upload_profile_id": project_profile.upload_profile_id,
            "lab_unit_id": binding.lab_unit_id,
        }

    encounter = _encounter_for_binding(db, exam, binding, mapped_metadata, encounters_by_binding, summary)
    try:
        content, content_type = client.download_file(_source_url(report), max_bytes=MAX_FILE_BYTES)
        if not _looks_like_pdf(content, content_type, report.remidio_path):
            raise RemidioRemoteError("Downloaded Remidio report is not a PDF.")
        filename = f"{uuid4()}.pdf"
        folder_rel = f"{_encounter_set_folder_rel(encounter)}/attachments"
        target_path = BASE_DIR / folder_rel / filename
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(content)
        attachment = EncounterSetAttachment(
            patient_encounter_id=encounter.id,
            uuid=str(uuid4()),
            asset_kind="pdf",
            original_filename=filename,
            stored_filename=filename,
            folder_rel=folder_rel,
            mime_type="application/pdf",
            file_size_bytes=len(content),
            is_pii=True,
            visible_to_grader=False,
            creates_task=False,
            project_id=encounter.project_id,
            upload_profile_id=encounter.upload_profile_id,
            hospital_id=binding.lab_unit.hospital_id if binding.lab_unit else None,
            metadata_json=_report_metadata(mapped_metadata, report.remidio_report_id),
        )
        db.add(attachment)
        db.flush()

        report.encounter_set_attachment_id = attachment.id
        report.downloaded_at = utcnow()
        report.download_error = None
        db.flush()
        summary.reports_downloaded += 1
        return {
            "remidio_report_id": report.remidio_report_id,
            "status": "downloaded",
            "patient_encounter_id": encounter.id,
            "encounter_set_attachment_id": attachment.id,
            "filename": filename,
        }
    except (OSError, RemidioIntegrationError) as exc:
        summary.download_errors += 1
        summary.reports_skipped += 1
        report.download_error = str(sanitize_log_value(exc))[:1000]
        return {"remidio_report_id": report.remidio_report_id, "status": "download_error", "error": report.download_error}


def _resolve_report_binding(
    db: Session,
    *,
    exam: RemidioExam,
    report: RemidioReport,
) -> ProjectUploadProfileRemidioApiBinding | None:
    linked_ids = _linked_report_image_ids(report)
    bindings: dict[int, ProjectUploadProfileRemidioApiBinding] = {}
    if linked_ids:
        linked_images = [image for image in exam.images if image.remidio_image_id in linked_ids]
        for image in linked_images:
            binding = resolve_binding_for_image(db, exam=exam, device_type=image.device_type)
            if binding is not None:
                bindings[binding.id] = binding
    else:
        for device_type in exam.device_types or []:
            binding = resolve_binding_for_image(db, exam=exam, device_type=device_type)
            if binding is not None:
                bindings[binding.id] = binding
    return next(iter(bindings.values())) if len(bindings) == 1 else None


def _encounter_for_binding(
    db: Session,
    exam: RemidioExam,
    binding: ProjectUploadProfileRemidioApiBinding,
    mapped_metadata,
    encounters_by_binding: dict[int, PatientEncounters],
    summary: IngestSummary,
) -> PatientEncounters:
    if binding.id in encounters_by_binding:
        return encounters_by_binding[binding.id]
    association = (
        db.query(RemidioApiExamEncounter)
        .options(selectinload(RemidioApiExamEncounter.patient_encounter))
        .filter(
            RemidioApiExamEncounter.remidio_exam_id == exam.id,
            RemidioApiExamEncounter.project_upload_profile_id == binding.project_upload_profile_id,
            RemidioApiExamEncounter.remidio_api_binding_id == binding.id,
        )
        .one_or_none()
    )
    if association is not None:
        summary.encounters_reused += 1
        encounters_by_binding[binding.id] = association.patient_encounter
        return association.patient_encounter

    encounter = _create_encounter(db, exam, binding, mapped_metadata)
    db.add(
        RemidioApiExamEncounter(
            remidio_exam_id=exam.id,
            patient_encounter_id=encounter.id,
            project_upload_profile_id=binding.project_upload_profile_id,
            remidio_api_binding_id=binding.id,
        )
    )
    if exam.patient_encounter_id is None:
        exam.patient_encounter_id = encounter.id
    _upsert_target_diseases(db, encounter, binding)
    db.flush()
    summary.encounters_created += 1
    encounters_by_binding[binding.id] = encounter
    return encounter


def _create_encounter(
    db: Session,
    exam: RemidioExam,
    binding: ProjectUploadProfileRemidioApiBinding,
    mapped_metadata,
) -> PatientEncounters:
    project_profile = binding.project_profile
    default_target_id = _default_image_scheme_id(binding)
    encounter = PatientEncounters(
        uuid=str(uuid4()),
        is_set_based=True,
        name=_encounter_patient_name(exam),
        patient_id=exam.remidio_patient_mrn or exam.remidio_patient_id or f"remidio-{exam.remidio_exam_id}",
        capture_date=_capture_date_string(exam),
        capture_date_dt=_capture_date(exam),
        lab_unit_id=binding.lab_unit_id,
        project_id=project_profile.project_id,
        upload_profile_id=project_profile.upload_profile_id,
        disease_id=default_target_id,
        metadata_json={
            "patient": mapped_metadata.patient,
            "encounter": mapped_metadata.encounter,
            "remidio_exam_row_id": exam.id,
            "remidio_exam_id": exam.remidio_exam_id,
            "remidio_api_binding_id": binding.id,
            "project_upload_profile_id": binding.project_upload_profile_id,
        },
    )
    db.add(encounter)
    db.flush()
    return encounter


def _upsert_target_diseases(db: Session, encounter: PatientEncounters, binding: ProjectUploadProfileRemidioApiBinding) -> None:
    target_defaults = _target_disease_defaults(binding)
    if not target_defaults:
        return
    existing = {
        row[0]
        for row in db.execute(
            select(PatientEncounterTargetDisease.disease_id).where(
                PatientEncounterTargetDisease.patient_encounter_id == encounter.id
            )
        ).all()
    }
    for disease_id, is_default in target_defaults.items():
        if disease_id not in existing:
            db.add(
                PatientEncounterTargetDisease(
                    patient_encounter_id=encounter.id,
                    disease_id=disease_id,
                    is_default=is_default,
                )
            )


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


def _linked_report_image_ids(report: RemidioReport) -> set[str]:
    raw = report.raw_json or {}
    if not isinstance(raw, dict):
        return set()
    values = raw.get("imageIds") or raw.get("image_ids") or raw.get("linkedImageIds")
    if not isinstance(values, list):
        return set()
    return {str(value).strip() for value in values if str(value).strip()}


def _target_disease_defaults(binding: ProjectUploadProfileRemidioApiBinding) -> dict[int, bool]:
    config = _remidio_profile_config(binding)
    if config is None:
        return {}
    defaults: dict[int, bool] = {}
    for scheme in config.image_grading_schemes:
        if scheme.active:
            defaults[scheme.disease_id] = scheme.disease_id == config.default_image_grading_scheme_id
    if config.encounter_grading_scheme_id:
        defaults.setdefault(config.encounter_grading_scheme_id, False)
    return defaults


def _default_image_scheme_id(binding: ProjectUploadProfileRemidioApiBinding) -> int | None:
    config = _remidio_profile_config(binding)
    return config.default_image_grading_scheme_id if config else None


def _remidio_profile_config(binding: ProjectUploadProfileRemidioApiBinding):
    profile = binding.project_profile.profile if binding.project_profile else None
    if not profile:
        return None
    for config in profile.encounter_set_types:
        if config.active and config.encounter_set_type and config.encounter_set_type.code == "remidio_api_standard":
            return config
    return None


def _image_metadata(mapped_metadata, remidio_image_id: str) -> dict[str, Any]:
    for image in mapped_metadata.images:
        if image.source_image_id == remidio_image_id:
            return image.metadata
    return {"remidio_image_id": remidio_image_id}


def _report_metadata(mapped_metadata, remidio_report_id: str) -> dict[str, Any]:
    for report in mapped_metadata.reports:
        if report.source_report_id == remidio_report_id:
            return report.metadata
    return {"remidio_report_id": remidio_report_id}


def _next_spatial_position(db: Session, patient_encounter_id: int) -> int:
    current_max = (
        db.execute(
            select(func.max(EncounterSetImage.spatial_position)).where(
                EncounterSetImage.patient_encounter_id == patient_encounter_id
            )
        ).scalar()
        or 0
    )
    return int(current_max) + 1


def _encounter_set_folder_rel(encounter: PatientEncounters) -> str:
    date_str = utcnow().strftime("%Y_%m_%d")
    return f"files/encounter_sets/{date_str}/{encounter.id}"


def _generate_encounter_set_thumbnail(image_path: Path, filename: str) -> str | None:
    try:
        thumbnail_filename = get_thumbnail_filename(filename)
        thumbnail_dir = image_path.parent / "thumbnails"
        thumbnail_dir.mkdir(parents=True, exist_ok=True)
        if generate_thumbnail(image_path, thumbnail_dir / thumbnail_filename):
            return thumbnail_filename
    except (OSError, UnidentifiedImageError) as exc:
        logger.info("Remidio EncounterSet thumbnail generation failed: %s", sanitize_log_value(exc))
        return None
    return None


def _site_identifier(exam: RemidioExam) -> str | None:
    if exam.site_custom_identifier:
        return exam.site_custom_identifier
    if exam.site and exam.site.site_custom_identifier:
        return exam.site.site_custom_identifier
    return None


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
    except (OSError, UnidentifiedImageError, ValueError) as exc:
        logger.info("Remidio image EXIF strip failed; storing original bytes: %s", sanitize_log_value(exc))
        return content


def _looks_like_pdf(content: bytes, content_type: str | None, path: str | None) -> bool:
    content_type = (content_type or "").lower().split(";")[0].strip()
    if content.startswith(b"%PDF"):
        return True
    if content_type == "application/pdf":
        return True
    return Path((path or "").split("?", 1)[0]).suffix.lower() == ".pdf"


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
