"""Small DTOs used between Remidio integration modules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class RemidioSecrets:
    base_url: str
    client_name: str
    client_identification_token: str
    email: str
    password: str


@dataclass(frozen=True)
class RemidioImagePayload:
    remidio_image_id: str
    device_type: str | None
    image_bucket: str | None
    image_variant: str | None
    laterality: str | None
    field: str | None
    quality: str | None
    width: int | None
    height: int | None
    remidio_path: str | None
    remidio_thumbnail_path: str | None
    raw_json: dict[str, Any]


@dataclass(frozen=True)
class RemidioReportPayload:
    remidio_report_id: str
    report_type: str
    report_local_id: str | None
    generated_date_ms: int | None
    generated_at: datetime | None
    remidio_path: str | None
    raw_json: dict[str, Any]


@dataclass(frozen=True)
class RemidioExamPayload:
    remidio_exam_id: str
    site_custom_identifier: str | None
    remidio_numeric_site_id: str | None
    remidio_patient_id: str | None
    remidio_patient_mrn: str | None
    exam_local_id: str | None
    exam_custom_id: str | None
    device_types: list[str]
    exam_state: str | None
    exam_date_ms: int | None
    exam_date: datetime | None
    pull_source: str
    raw_json: dict[str, Any]
    images: list[RemidioImagePayload]
    reports: list[RemidioReportPayload]


@dataclass(frozen=True)
class UpsertSummary:
    exams_seen: int = 0
    exams_created: int = 0
    exams_updated: int = 0
    images_seen: int = 0
    images_created: int = 0
    images_updated: int = 0
    reports_seen: int = 0
    reports_created: int = 0
    reports_updated: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "exams_seen": self.exams_seen,
            "exams_created": self.exams_created,
            "exams_updated": self.exams_updated,
            "images_seen": self.images_seen,
            "images_created": self.images_created,
            "images_updated": self.images_updated,
            "reports_seen": self.reports_seen,
            "reports_created": self.reports_created,
            "reports_updated": self.reports_updated,
        }
