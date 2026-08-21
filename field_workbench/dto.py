"""Typed contracts for the field staff surface.

These DTOs are the whole projection the field app sees. Everything absent here
is deliberately withheld: staging rows, remote object keys, signed URLs, request
and response manifests, config snapshots, raw provider logits and similarity
scores. Field staff get a clinical answer, not the ingestion record.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any

FIELD_SCHEMA_VERSION = 1

# Sources that land encounters into this system.
SOURCE_REMIDIO = "remidio"
SOURCE_IITK = "iitk"


def _iso(value: datetime | date | None) -> str | None:
    return value.isoformat() if value is not None else None


@dataclass(frozen=True)
class FieldProjectDTO:
    id: int
    title: str
    code: str
    active: bool
    roles: tuple[str, ...] = ()
    # Which AI workflows this project's policy actually enables, so the client
    # can hide a request button rather than discover a 409 by pressing it.
    ai_workflows: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()
    can_request_inference: bool = False
    can_trigger_fetch: bool = False

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["roles"] = list(self.roles)
        data["ai_workflows"] = list(self.ai_workflows)
        data["sources"] = list(self.sources)
        return data


@dataclass(frozen=True)
class AIEyeResultDTO:
    eye: str
    grade: str | None
    positive: bool
    gradable: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AIStatusDTO:
    """One disease answer, rolled up to the patient."""

    kind: str  # dr | dme | glaucoma
    label: str
    run_status: str  # not_requested | queued | running | success | partial | failed
    patient_result: str  # positive | negative | not_gradable | pending
    eyes: tuple[AIEyeResultDTO, ...] = ()
    model: str | None = None
    requestable: bool = False
    reason: str | None = None
    updated_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "label": self.label,
            "run_status": self.run_status,
            "patient_result": self.patient_result,
            "eyes": [eye.to_dict() for eye in self.eyes],
            "model": self.model,
            "requestable": self.requestable,
            "reason": self.reason,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class RemidioReportDTO:
    """The camera's own AI report.

    The PDF and the OCR-derived structure are deliberately decoupled: the PDF is
    offered the moment it lands, because making field staff wait for OCR to read
    a report they could already open would be a needless delay.
    """

    pdf_available: bool
    pdf_url: str | None
    ocr_status: str  # pending | completed | failed | absent
    ocr_result: str | None = None
    report_datetime: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FieldImageDTO:
    uuid: str
    position: int
    eye: str | None
    focus: str | None
    gaze_position: str | None = None
    is_not_gradable: bool = False
    thumbnail_url: str | None = None
    image_url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FieldEncounterRowDTO:
    uuid: str
    source: str
    patient_id: str | None
    patient_name: str | None
    capture_date: str | None
    lab_unit: str | None
    image_count: int
    verified_status: str | None
    ai: tuple[AIStatusDTO, ...] = ()
    report: RemidioReportDTO | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "uuid": self.uuid,
            "source": self.source,
            "patient_id": self.patient_id,
            "patient_name": self.patient_name,
            "capture_date": self.capture_date,
            "lab_unit": self.lab_unit,
            "image_count": self.image_count,
            "verified_status": self.verified_status,
            "ai": [item.to_dict() for item in self.ai],
            "report": self.report.to_dict() if self.report else None,
        }


@dataclass(frozen=True)
class FieldEncounterDetailDTO:
    uuid: str
    source: str
    project_id: int
    patient_id: str | None
    patient_name: str | None
    patient_age: str | None
    patient_sex: str | None
    capture_date: str | None
    lab_unit: str | None
    verified_status: str | None
    referral_suggestion: str | None
    images: tuple[FieldImageDTO, ...] = ()
    ai: tuple[AIStatusDTO, ...] = ()
    report: RemidioReportDTO | None = None
    schema_version: int = FIELD_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "uuid": self.uuid,
            "source": self.source,
            "project_id": self.project_id,
            "patient_id": self.patient_id,
            "patient_name": self.patient_name,
            "patient_age": self.patient_age,
            "patient_sex": self.patient_sex,
            "capture_date": self.capture_date,
            "lab_unit": self.lab_unit,
            "verified_status": self.verified_status,
            "referral_suggestion": self.referral_suggestion,
            "images": [image.to_dict() for image in self.images],
            "ai": [item.to_dict() for item in self.ai],
            "report": self.report.to_dict() if self.report else None,
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True)
class FieldEncounterDateDTO:
    date: str
    count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FetchStatusDTO:
    """State of one upstream source's fetch for one project.

    Counts and state only - never routing profiles, bindings, connection
    identifiers, or job item payloads.
    """

    source: str
    running: bool
    state: str  # idle | queued | running | completed | failed | partial | not_configured
    last_attempt_at: str | None = None
    last_success_at: str | None = None
    last_error: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)
    incomplete_count: int = 0
    can_retry: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
