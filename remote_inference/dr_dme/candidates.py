"""Scoped search contracts and query composition for DR/DME encounter work."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from models import EncounterSetImage, PatientEncounters
from remote_inference.dr_dme_service import evaluate_encounter
from remote_inference.models import EncounterAIInferenceRun, ProjectEncounterAIWorkflow
from utils.hospital_scoping import apply_scoping


ALLOWED_PAGE_SIZES = (25, 50, 75, 100)
MAX_MANUAL_ENCOUNTERS = 100
ELIGIBILITY_FILTERS = {"any", "eligible", "not_verified", "binocular_one_eye"}


def validate_selection_count(count: int) -> str | None:
    if 1 <= count <= MAX_MANUAL_ENCOUNTERS:
        return None
    return f"Select between 1 and {MAX_MANUAL_ENCOUNTERS} EncounterSets."


@dataclass(frozen=True)
class CandidateFilters:
    project_id: int
    encounter_ids: tuple[int, ...] = ()
    capture_date_from: str = ""
    capture_date_to: str = ""
    camera_id: str = ""
    dr_report: str = ""
    eligibility: str = "eligible"
    include_prior: bool = False
    page: int = 1
    page_size: int = 25

    def normalized(self) -> "CandidateFilters":
        return CandidateFilters(
            project_id=self.project_id,
            encounter_ids=tuple(dict.fromkeys(self.encounter_ids)),
            capture_date_from=self.capture_date_from,
            capture_date_to=self.capture_date_to,
            camera_id=self.camera_id,
            dr_report=self.dr_report if self.dr_report in {"", "present", "absent"} else "",
            eligibility=self.eligibility if self.eligibility in ELIGIBILITY_FILTERS else "eligible",
            include_prior=self.include_prior,
            page=max(self.page, 1),
            page_size=self.page_size if self.page_size in ALLOWED_PAGE_SIZES else ALLOWED_PAGE_SIZES[0],
        )


@dataclass(frozen=True)
class CandidatePage:
    rows: tuple[dict[str, Any], ...]
    encounter_count: int
    image_count: int
    page: int
    page_size: int
    has_prev: bool
    has_next: bool

    @property
    def prev_page(self) -> int:
        return max(self.page - 1, 1)

    @property
    def next_page(self) -> int:
        return self.page + 1


def _date_value(raw: str) -> date | None:
    try:
        return date.fromisoformat(raw)
    except (TypeError, ValueError):
        return None


def _dr_report_summary(encounter: PatientEncounters) -> dict[str, Any] | None:
    for attachment in encounter.encounter_set_attachments or []:
        metadata = attachment.metadata_json if isinstance(attachment.metadata_json, dict) else {}
        ocr = metadata.get("ocr") if isinstance(metadata.get("ocr"), dict) else {}
        report = ocr.get("dr_report")
        if not report:
            continue
        if isinstance(report, dict):
            status = str(ocr.get("status") or report.get("status") or "").lower()
            return {
                "status": status or "available",
                "result": report.get("result") or report.get("impression") or report.get("classification"),
                "attachment_filename": attachment.original_filename,
            }
        return {
            "status": str(ocr.get("status") or "available").lower(),
            "result": str(report),
            "attachment_filename": attachment.original_filename,
        }
    return None


def _matches_eligibility_filter(eligibility: Any, value: str) -> bool:
    if value == "eligible":
        return bool(eligibility.eligible)
    if value == "not_verified":
        return not eligibility.is_verified
    if value == "binocular_one_eye":
        return (
            not eligibility.is_monocular
            and sum(count > 0 for count in eligibility.eye_counts.values()) == 1
        )
    return True


def list_candidates(db, *, filters: CandidateFilters, user: Any) -> CandidatePage:
    """Return a scoped, filtered page while preserving whole-encounter eligibility."""
    filters = filters.normalized()
    workflow = db.execute(
        select(ProjectEncounterAIWorkflow).where(
            ProjectEncounterAIWorkflow.project_id == filters.project_id,
            ProjectEncounterAIWorkflow.workflow_key == "dr_dme",
            ProjectEncounterAIWorkflow.active.is_(True),
            ProjectEncounterAIWorkflow.manual_enabled.is_(True),
        )
    ).scalar_one_or_none()
    if workflow is None:
        return CandidatePage((), 0, 0, filters.page, filters.page_size, filters.page > 1, False)

    query = (
        db.query(PatientEncounters)
        .options(
            selectinload(PatientEncounters.lab_unit),
            selectinload(PatientEncounters.encounter_set_attachments),
            selectinload(PatientEncounters.encounter_set_images).selectinload(EncounterSetImage.camera),
        )
        .filter(
            PatientEncounters.project_id == filters.project_id,
            PatientEncounters.is_set_based.is_(True),
        )
        .order_by(PatientEncounters.capture_date_dt.desc().nullslast(), PatientEncounters.id.desc())
    )
    date_from = _date_value(filters.capture_date_from)
    date_to = _date_value(filters.capture_date_to)
    if date_from:
        query = query.filter(PatientEncounters.capture_date_dt >= date_from)
    if date_to:
        query = query.filter(PatientEncounters.capture_date_dt <= date_to)
    if filters.encounter_ids:
        query = query.filter(PatientEncounters.id.in_(filters.encounter_ids))
    encounters = apply_scoping(query, PatientEncounters, user, "upload").all()

    runs = db.execute(
        select(EncounterAIInferenceRun).where(
            EncounterAIInferenceRun.patient_encounter_id.in_([row.id for row in encounters]),
            EncounterAIInferenceRun.ai_model_id == workflow.ai_model_id,
        )
    ).scalars().all() if encounters else []
    run_by_encounter = {row.patient_encounter_id: row for row in runs}

    rows: list[dict[str, Any]] = []
    image_count = 0
    for encounter in encounters:
        run = run_by_encounter.get(encounter.id)
        if run is not None and not filters.include_prior:
            continue
        report = _dr_report_summary(encounter)
        if filters.dr_report == "present" and report is None:
            continue
        if filters.dr_report == "absent" and report is not None:
            continue
        eligibility = evaluate_encounter(encounter, require_verified=True)
        if not _matches_eligibility_filter(eligibility, filters.eligibility):
            continue
        eligible_ids = {row.image_id: row for row in eligibility.images}
        images = []
        for image in sorted(encounter.encounter_set_images or [], key=lambda row: (row.spatial_position, row.id)):
            eligible = eligible_ids.get(image.id)
            if eligible is None:
                continue
            metadata = image.metadata_json if isinstance(image.metadata_json, dict) else {}
            images.append({
                "id": image.id,
                "uuid": image.uuid,
                "position": image.spatial_position,
                "eye": eligible.eye,
                "camera_id": image.camera_id,
                "camera_name": image.camera.name if image.camera else None,
                "focus": "macula",
                "variant": metadata.get("variant"),
                "quality": metadata.get("quality"),
            })
        if filters.camera_id and not any(str(row["camera_id"] or "") == filters.camera_id for row in images):
            continue
        image_count += len(images)
        rows.append({
            "encounter_id": encounter.id,
            "encounter_uuid": encounter.uuid,
            "patient_id": encounter.patient_id,
            "patient_age": eligibility.age,
            "patient_sex": eligibility.sex,
            "is_monocular": eligibility.is_monocular,
            "capture_date": encounter.capture_date_dt or encounter.capture_date,
            "lab_unit_name": encounter.lab_unit.name if encounter.lab_unit else None,
            "eligible": eligibility.eligible,
            "eligibility_issues": list(eligibility.issues),
            "eye_counts": eligibility.eye_counts,
            "images": images,
            "dr_report": report,
            "run_status": run.status if run else "not_requested",
            "report_id": run.report_id if run else None,
            "has_prior": run is not None,
        })

    encounter_count = len(rows)
    start = (filters.page - 1) * filters.page_size
    page_rows = tuple(rows[start : start + filters.page_size])
    return CandidatePage(
        rows=page_rows,
        encounter_count=encounter_count,
        image_count=image_count,
        page=filters.page,
        page_size=filters.page_size,
        has_prev=filters.page > 1,
        has_next=start + filters.page_size < encounter_count,
    )
