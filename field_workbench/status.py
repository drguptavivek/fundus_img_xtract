"""Resolve the Remidio report and WAI answers for an encounter, at patient level.

Three sources feed this, each shaped differently:

- The Remidio report is a PDF attachment plus, separately and later, an OCR
  result. They are reported independently so the PDF is never gated on OCR.
- WAI DR/DME is one encounter-scoped ``EncounterAIInferenceRun``, whose per-eye
  answer lives on the single ``is_primary`` image for that eye.
- WAI Glaucoma has no encounter-level run at all: it is task-scoped, one
  ``AIInferenceRun`` per image task, so both status and result are aggregated.

Per-image detail stays internal. Field staff need the patient's answer.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from models import (
    AIInferenceRun,
    AIModel,
    Disease,
    EncounterSetImage,
    Grade,
    GradingTask,
    PatientEncounters,
)
from remote_inference.encounter_service import is_positive_output
from remote_inference.models import (
    EncounterAIImageResult,
    EncounterAIInferenceRun,
    EncounterAITargetResult,
)

from .dto import AIEyeResultDTO, AIStatusDTO, RemidioReportDTO

logger = logging.getLogger("field_workbench.status")

WAI_LABELS = {"dr": "WAI-DR", "dme": "WAI-DME", "glaucoma": "WAI-Glau"}
OCR_COMPLETE_STATES = {"completed", "success", "ok"}
NOT_GRADABLE_LABELS = {"not gradable", "ungradable"}

# A DR/DME run in one of these states has work outstanding, so a re-request must
# not enqueue a duplicate.
DR_DME_ACTIVE_STATES = {"queued", "presigning", "uploading", "submitting"}


@dataclass(frozen=True)
class WaiDiseaseKind:
    key: str
    label: str


def wai_disease_kind(disease: Disease) -> str | None:
    """Map a Disease onto a WAI pill key.

    ``remidio_ocr_linkage`` is the intended signal, with an exact name match as
    a fallback for diseases whose linkage was never configured (the seeded
    DR/Glaucoma rows default it to 'none').
    """
    linkage = (getattr(disease, "remidio_ocr_linkage", None) or "none").lower()
    name = (disease.name or "").strip().lower()
    if linkage == "dr" or name == "dr":
        return "dr"
    if linkage == "glaucoma" or name == "glaucoma":
        return "glaucoma"
    if name == "dme":
        return "dme"
    return None


def encounter_wai_grades_by_image(db, encounter_id: int) -> dict[int, dict[str, str]]:
    """Map image id -> {kind: "model vX"} for images carrying an AI-role grade.

    ``Grade.role_slot == 'ai'`` is written only by the two WAI pipelines -
    ``remote_inference/dr_dme_service.py`` and
    ``services/encounter_set_ai_inference.py`` - never by the separate Remidio
    OCR/PDF report sync, which writes report rows and no Grade. Do not widen
    this to include those reports.

    ``Grade.ai_model_id`` is used rather than the denormalized
    ``ai_model_name``/``ai_model_version`` columns, which the Glaucoma pipeline
    leaves null.
    """
    rows = (
        db.query(GradingTask.encounter_set_image_id, Disease, AIModel)
        .join(Grade, Grade.task_id == GradingTask.id)
        .join(Disease, Disease.id == GradingTask.disease_id)
        .join(EncounterSetImage, EncounterSetImage.id == GradingTask.encounter_set_image_id)
        .outerjoin(AIModel, AIModel.id == Grade.ai_model_id)
        .filter(
            EncounterSetImage.patient_encounter_id == encounter_id,
            Grade.role_slot == "ai",
        )
        .distinct()
        .all()
    )
    by_image: dict[int, dict[str, str]] = {}
    for image_id, disease, ai_model in rows:
        kind = wai_disease_kind(disease)
        if kind is None or image_id is None:
            continue
        label = f"{ai_model.name} v{ai_model.version}" if ai_model else "Unknown model"
        by_image.setdefault(image_id, {})[kind] = label
    return by_image


def _roll_up(eyes: list[AIEyeResultDTO], *, run_finished: bool) -> str:
    if not eyes:
        return "pending" if not run_finished else "not_gradable"
    if any(eye.positive for eye in eyes):
        return "positive"
    if not any(eye.gradable for eye in eyes):
        # Both eyes ungradable is not a negative finding - it is no finding.
        return "not_gradable"
    return "negative"


def _normalize_eye(value: Any) -> str | None:
    raw = str(value or "").strip().lower()
    if raw in {"od", "r", "right", "right eye"}:
        return "right"
    if raw in {"os", "l", "left", "left eye"}:
        return "left"
    return None


def dr_dme_statuses(db, encounter: PatientEncounters, *, workflow_enabled: bool) -> list[AIStatusDTO]:
    """DR and DME reported separately, from the one combined run."""
    run = db.execute(
        select(EncounterAIInferenceRun)
        .options(
            selectinload(EncounterAIInferenceRun.image_results)
            .selectinload(EncounterAIImageResult.target_results)
            .selectinload(EncounterAITargetResult.output_target),
            selectinload(EncounterAIInferenceRun.ai_model),
        )
        .where(EncounterAIInferenceRun.patient_encounter_id == encounter.id)
        .order_by(EncounterAIInferenceRun.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    model_label = None
    if run is not None and run.ai_model is not None:
        model_label = f"{run.ai_model.name} v{run.ai_model.version}"

    if run is None:
        run_status = "not_requested"
    elif run.status in DR_DME_ACTIVE_STATES:
        run_status = "running" if run.status != "queued" else "queued"
    else:
        run_status = run.status

    finished = run_status in {"success", "partial", "failed"}
    requestable = workflow_enabled and run_status in {"not_requested", "failed"}
    reason = None
    if not workflow_enabled:
        reason = "workflow_disabled"
    elif not requestable:
        reason = "already_present"

    # Per eye, read the single is_primary image. The vendor contract is explicit
    # that eye-level grading comes from that entry, never from image order.
    per_kind_eyes: dict[str, list[AIEyeResultDTO]] = {"dr": [], "dme": []}
    if run is not None:
        for image_result in run.image_results:
            if not image_result.is_primary:
                continue
            eye = image_result.submitted_eye
            for target in image_result.target_results:
                key = getattr(target.output_target, "target_key", None)
                if key not in per_kind_eyes:
                    continue
                grade = target.mapped_grade
                gradable = str(grade or "").strip().lower() not in NOT_GRADABLE_LABELS
                per_kind_eyes[key].append(
                    AIEyeResultDTO(
                        eye=eye,
                        grade=grade,
                        positive=bool(gradable and is_positive_output(key, grade)),
                        gradable=gradable,
                    )
                )

    out = []
    for key in ("dr", "dme"):
        eyes = sorted(per_kind_eyes[key], key=lambda item: item.eye)
        if run_status in {"not_requested", "queued", "running"}:
            patient_result = "pending"
        else:
            patient_result = _roll_up(eyes, run_finished=finished)
        out.append(
            AIStatusDTO(
                kind=key,
                label=WAI_LABELS[key],
                run_status=run_status,
                patient_result=patient_result,
                eyes=tuple(eyes),
                model=model_label,
                requestable=requestable,
                reason=reason,
                updated_at=run.updated_at.isoformat() if run is not None and run.updated_at else None,
            )
        )
    return out


def glaucoma_status(db, encounter: PatientEncounters, *, workflow_enabled: bool) -> AIStatusDTO:
    """Aggregate the task-scoped glaucoma runs into one patient-level answer."""
    rows = db.execute(
        select(AIInferenceRun, GradingTask, EncounterSetImage, AIModel)
        .join(GradingTask, GradingTask.id == AIInferenceRun.task_id)
        .join(EncounterSetImage, EncounterSetImage.id == GradingTask.encounter_set_image_id)
        .join(Disease, Disease.id == GradingTask.disease_id)
        .outerjoin(AIModel, AIModel.id == AIInferenceRun.ai_model_id)
        .where(EncounterSetImage.patient_encounter_id == encounter.id)
        .where(Disease.name.ilike("glaucoma"))
        .order_by(AIInferenceRun.created_at.desc())
    ).all()

    if not rows:
        run_status = "not_requested"
    else:
        # The glaucoma pipeline also writes "skipped" rows (image not
        # eligible), so a completed encounter is any mix of success and
        # skipped — never require an all-success set.
        statuses = {row[0].status for row in rows}
        if "failed" in statuses:
            run_status = "failed"
        elif statuses & {"queued", "running"}:
            run_status = "running" if "running" in statuses else "queued"
        elif "success" in statuses:
            run_status = "success"
        else:
            run_status = "not_requested"

    model_label = None
    for _, _, _, ai_model in rows:
        if ai_model is not None:
            model_label = f"{ai_model.name} v{ai_model.version}"
            break

    # Glaucoma has no is_primary, so an eye is positive if any of its images is.
    by_eye: dict[str, dict[str, Any]] = {}
    grades = db.execute(
        select(Grade, EncounterSetImage)
        .join(GradingTask, GradingTask.id == Grade.task_id)
        .join(EncounterSetImage, EncounterSetImage.id == GradingTask.encounter_set_image_id)
        .join(Disease, Disease.id == GradingTask.disease_id)
        .where(EncounterSetImage.patient_encounter_id == encounter.id)
        .where(Grade.role_slot == "ai")
        .where(Disease.name.ilike("glaucoma"))
    ).all()
    for grade, image in grades:
        metadata = image.metadata_json if isinstance(image.metadata_json, dict) else {}
        eye = _normalize_eye(
            metadata.get("laterality") or metadata.get("eye") or metadata.get("eye_side")
        )
        if eye is None:
            continue
        label = str(getattr(grade, "impression", None) or "").strip()
        gradable = label.lower() not in NOT_GRADABLE_LABELS and bool(label)
        positive = gradable and label.lower() not in {"normal", "no glaucoma"}
        current = by_eye.setdefault(eye, {"grade": label or None, "positive": False, "gradable": False})
        current["gradable"] = current["gradable"] or gradable
        if positive:
            current["positive"] = True
            current["grade"] = label

    eyes = tuple(
        AIEyeResultDTO(eye=eye, grade=data["grade"], positive=data["positive"], gradable=data["gradable"])
        for eye, data in sorted(by_eye.items())
    )
    if run_status in {"not_requested", "queued", "running"}:
        patient_result = "pending"
    else:
        patient_result = _roll_up(list(eyes), run_finished=run_status in {"success", "failed"})

    requestable = workflow_enabled and run_status in {"not_requested", "failed"}
    reason = None
    if not workflow_enabled:
        reason = "workflow_disabled"
    elif not requestable:
        reason = "already_present"

    return AIStatusDTO(
        kind="glaucoma",
        label=WAI_LABELS["glaucoma"],
        run_status=run_status,
        patient_result=patient_result,
        eyes=eyes,
        model=model_label,
        requestable=requestable,
        reason=reason,
        updated_at=rows[0][0].updated_at.isoformat() if rows and rows[0][0].updated_at else None,
    )


def remidio_report(encounter: PatientEncounters, *, pdf_url: str | None) -> RemidioReportDTO | None:
    """The camera's report: PDF as soon as it lands, OCR structure when ready."""
    pdf_attachment = None
    ocr_status = "absent"
    ocr_result = None
    report_datetime = None

    for attachment in encounter.encounter_set_attachments or []:
        is_pdf = attachment.asset_kind in {"pdf", "document", "document_image"} or (
            attachment.mime_type == "application/pdf"
        )
        if is_pdf and pdf_attachment is None:
            pdf_attachment = attachment
        metadata = attachment.metadata_json if isinstance(attachment.metadata_json, dict) else {}
        ocr = metadata.get("ocr") if isinstance(metadata.get("ocr"), dict) else {}
        if not ocr:
            continue
        status = str(ocr.get("status") or "").lower()
        report = ocr.get("dr_report")
        if status in OCR_COMPLETE_STATES and report:
            ocr_status = "completed"
            if isinstance(report, dict):
                ocr_result = (
                    report.get("result") or report.get("impression") or report.get("classification")
                )
            else:
                ocr_result = str(report)
            report_datetime = ocr.get("source_report_datetime") or ocr.get("completed_at")
        elif ocr_status == "completed":
            # A real encounter carries several attachments. Once one has produced
            # a report, a later still-queued attachment must not drag the status
            # back to pending while the result from the first one is still shown.
            continue
        elif status in {"failed", "error"}:
            ocr_status = "failed"
        elif status:
            ocr_status = "pending"

    if pdf_attachment is None and ocr_status == "absent":
        return None

    # The PDF is offered the moment the attachment exists. Waiting for OCR would
    # withhold a report the field user could already read.
    if pdf_attachment is not None and ocr_status == "absent":
        ocr_status = "pending"

    return RemidioReportDTO(
        pdf_available=pdf_attachment is not None,
        pdf_url=pdf_url if pdf_attachment is not None else None,
        ocr_status=ocr_status,
        ocr_result=ocr_result,
        report_datetime=str(report_datetime) if report_datetime else None,
    )
