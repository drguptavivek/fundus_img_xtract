"""Database writes for Remidio integration entities."""

from __future__ import annotations

from sqlalchemy.orm import Session

from auth.utils import utcnow
from models import RemidioExam, RemidioImage, RemidioReport, RemidioSite

from .schemas import RemidioExamPayload, UpsertSummary


def upsert_sites(db: Session, *, connection_id: int, sites: list[dict]) -> list[RemidioSite]:
    rows: list[RemidioSite] = []
    for site_payload in sites:
        row = (
            db.query(RemidioSite)
            .filter(
                RemidioSite.remidio_connection_id == connection_id,
                RemidioSite.remidio_site_id == site_payload["remidio_site_id"],
            )
            .one_or_none()
        )
        if row is None:
            row = RemidioSite(
                remidio_connection_id=connection_id,
                remidio_site_id=site_payload["remidio_site_id"],
            )
            db.add(row)
        row.site_name = site_payload.get("site_name")
        row.site_domain = site_payload.get("site_domain")
        row.raw_json = site_payload.get("raw_json")
        row.active = True
        row.updated_at = utcnow()
        rows.append(row)
    db.flush()
    return rows


def upsert_exam_payloads(db: Session, *, connection_id: int, payloads: list[RemidioExamPayload]) -> UpsertSummary:
    summary = _MutableSummary(exams_seen=len(payloads))
    site_cache = _site_cache(db, connection_id)

    for payload in payloads:
        exam = (
            db.query(RemidioExam)
            .filter(
                RemidioExam.remidio_connection_id == connection_id,
                RemidioExam.remidio_exam_id == payload.remidio_exam_id,
            )
            .one_or_none()
        )
        if exam is None:
            summary.exams_created += 1
            exam = RemidioExam(
                remidio_connection_id=connection_id,
                remidio_exam_id=payload.remidio_exam_id,
            )
            db.add(exam)
            db.flush()
        else:
            summary.exams_updated += 1

        exam.remidio_site_id = _resolve_site_id(site_cache, payload)
        exam.site_custom_identifier = payload.site_custom_identifier
        exam.remidio_numeric_site_id = payload.remidio_numeric_site_id
        exam.remidio_patient_id = payload.remidio_patient_id
        exam.remidio_patient_mrn = payload.remidio_patient_mrn
        exam.exam_local_id = payload.exam_local_id
        exam.exam_custom_id = payload.exam_custom_id
        exam.device_types = payload.device_types
        exam.exam_state = payload.exam_state
        exam.exam_date_ms = payload.exam_date_ms
        exam.exam_date = payload.exam_date
        exam.pull_source = payload.pull_source
        exam.raw_json = payload.raw_json
        exam.pulled_at = utcnow()
        exam.updated_at = utcnow()
        db.flush()

        for image_payload in payload.images:
            summary.images_seen += 1
            image = (
                db.query(RemidioImage)
                .filter(
                    RemidioImage.remidio_exam_id == exam.id,
                    RemidioImage.remidio_image_id == image_payload.remidio_image_id,
                )
                .one_or_none()
            )
            if image is None:
                summary.images_created += 1
                image = RemidioImage(
                    remidio_exam_id=exam.id,
                    remidio_image_id=image_payload.remidio_image_id,
                )
                db.add(image)
            else:
                summary.images_updated += 1
            image.device_type = image_payload.device_type
            image.image_bucket = image_payload.image_bucket
            image.image_variant = image_payload.image_variant
            image.laterality = image_payload.laterality
            image.field = image_payload.field
            image.quality = image_payload.quality
            image.width = image_payload.width
            image.height = image_payload.height
            image.remidio_path = image_payload.remidio_path
            image.remidio_thumbnail_path = image_payload.remidio_thumbnail_path
            image.raw_json = image_payload.raw_json
            image.updated_at = utcnow()

        for report_payload in payload.reports:
            summary.reports_seen += 1
            report = (
                db.query(RemidioReport)
                .filter(
                    RemidioReport.remidio_exam_id == exam.id,
                    RemidioReport.remidio_report_id == report_payload.remidio_report_id,
                    RemidioReport.report_type == report_payload.report_type,
                )
                .one_or_none()
            )
            if report is None:
                summary.reports_created += 1
                report = RemidioReport(
                    remidio_exam_id=exam.id,
                    remidio_report_id=report_payload.remidio_report_id,
                    report_type=report_payload.report_type,
                )
                db.add(report)
            else:
                summary.reports_updated += 1
            report.report_local_id = report_payload.report_local_id
            report.generated_date_ms = report_payload.generated_date_ms
            report.generated_at = report_payload.generated_at
            report.remidio_path = report_payload.remidio_path
            report.raw_json = report_payload.raw_json
            report.updated_at = utcnow()

    db.flush()
    return summary.to_immutable()


def _site_cache(db: Session, connection_id: int) -> dict[str, int]:
    rows = db.query(RemidioSite).filter(RemidioSite.remidio_connection_id == connection_id).all()
    cache: dict[str, int] = {}
    for row in rows:
        cache[f"site_id:{row.remidio_site_id}"] = row.id
        if row.site_custom_identifier:
            cache[f"custom:{row.site_custom_identifier}"] = row.id
    return cache


def _resolve_site_id(cache: dict[str, int], payload: RemidioExamPayload) -> int | None:
    if payload.site_custom_identifier:
        site_id = cache.get(f"custom:{payload.site_custom_identifier}")
        if site_id:
            return site_id
    if payload.remidio_numeric_site_id:
        return cache.get(f"site_id:{payload.remidio_numeric_site_id}")
    return None


class _MutableSummary:
    def __init__(self, *, exams_seen: int) -> None:
        self.exams_seen = exams_seen
        self.exams_created = 0
        self.exams_updated = 0
        self.images_seen = 0
        self.images_created = 0
        self.images_updated = 0
        self.reports_seen = 0
        self.reports_created = 0
        self.reports_updated = 0

    def to_immutable(self) -> UpsertSummary:
        return UpsertSummary(
            exams_seen=self.exams_seen,
            exams_created=self.exams_created,
            exams_updated=self.exams_updated,
            images_seen=self.images_seen,
            images_created=self.images_created,
            images_updated=self.images_updated,
            reports_seen=self.reports_seen,
            reports_created=self.reports_created,
            reports_updated=self.reports_updated,
        )
