"""Automated AI inference policy for EncounterSet images."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import selectinload

from db_transaction_manager import transaction_scope
from job_store import db_create_job
from models import AIInferenceRun, AIModelIntegration, EncounterSetGradingPackage, Grade, GradingTask, PatientEncounters
from upload_profiles.models import UploadProfileAIWorkflow
from utils.celery_helpers import enqueue_task

DISC_FOCUSED_IMAGE_TERMS = (
    "disc",
    "disk",
    "optic disc",
    "optic disk",
    "optic nerve head",
    "onh",
)


def create_wadhwani_task_ids_for_encounter(db, encounter: PatientEncounters) -> list[int]:
    """Create/reuse Glaucoma image tasks for configured EncounterSet Wadhwani inference."""
    if not encounter.upload_profile_id:
        return []
    evidence = encounter_set_report_evidence(encounter)
    workflows = (
        db.query(UploadProfileAIWorkflow)
        .join(AIModelIntegration, AIModelIntegration.ai_model_id == UploadProfileAIWorkflow.ai_model_id)
        .filter(
            UploadProfileAIWorkflow.upload_profile_id == encounter.upload_profile_id,
            UploadProfileAIWorkflow.upload_kind == "encounter_set",
            UploadProfileAIWorkflow.active.is_(True),
            AIModelIntegration.provider == "wadhwani_glaucoma",
            AIModelIntegration.is_enabled.is_(True),
        )
        .all()
    )
    applicable_workflows: list[UploadProfileAIWorkflow] = []
    workflow_disease_scopes: dict[int, str] = {}
    for row in workflows:
        scope = _ai_workflow_task_scope(row.auto_inference_policy, evidence)
        if scope is None:
            continue
        applicable_workflows.append(row)
        if workflow_disease_scopes.get(row.disease_id) != "all":
            workflow_disease_scopes[row.disease_id] = scope
    if not workflow_disease_scopes:
        return []

    task_ids: list[int] = []
    for image in sorted(encounter.encounter_set_images or [], key=lambda item: (item.spatial_position, item.id)):
        if (
            image.asset_kind != "clinical_image"
            or not image.creates_task
            or not image.visible_to_grader
            or image.is_not_gradable
        ):
            continue
        for disease_id, scope in sorted(workflow_disease_scopes.items()):
            if scope == "disc" and not _is_disc_focused_encounter_set_image(image):
                continue
            task = (
                db.query(GradingTask)
                .filter(
                    GradingTask.encounter_set_image_id == image.id,
                    GradingTask.disease_id == disease_id,
                )
                .first()
            )
            if task is None:
                task = GradingTask(
                    encounter_set_image_id=image.id,
                    disease_id=disease_id,
                    lab_unit_id=encounter.lab_unit_id,
                    state="pending",
                    grading_target_level="image",
                    task_source="encounter_set_ai_inference",
                )
                db.add(task)
                db.flush()
            task_ids.append(task.id)
    return queueable_wadhwani_task_ids(db, task_ids, applicable_workflows)


def queueable_wadhwani_task_ids(db, task_ids: list[int], workflows: list[UploadProfileAIWorkflow]) -> list[int]:
    if not task_ids:
        return []
    model_ids = {workflow.ai_model_id for workflow in workflows}
    if not model_ids:
        return []
    already_graded = {
        row[0]
        for row in db.query(Grade.task_id)
        .filter(Grade.task_id.in_(task_ids), Grade.role_slot == "ai", Grade.ai_model_id.in_(model_ids))
        .all()
    }
    already_running = {
        row[0]
        for row in db.query(AIInferenceRun.task_id)
        .filter(
            AIInferenceRun.task_id.in_(task_ids),
            AIInferenceRun.ai_model_id.in_(model_ids),
            AIInferenceRun.status.in_(["queued", "running", "success"]),
        )
        .all()
    }
    excluded = already_graded.union(already_running)
    return [task_id for task_id in task_ids if task_id not in excluded]


def enqueue_wadhwani_for_task_ids(
    task_ids: list[int] | tuple[int, ...],
    *,
    user_id: int | None,
    username: str | None,
    remote_addr: str | None,
    lab_unit_id: int | None,
    project_id: int | None,
    upload_profile_id: int | None,
) -> str | None:
    if not task_ids:
        return None
    job_token = db_create_job(
        [f"task:{task_id}" for task_id in task_ids],
        [],
        uploader_user_id=user_id,
        uploader_username=username,
        uploader_ip=remote_addr,
        lab_unit_id=lab_unit_id,
        project_id=project_id,
        upload_type="encounter_set_wadhwani_inference",
        upload_kind="encounter_set",
        upload_profile_id=upload_profile_id,
    )
    enqueue_task(
        "celery_tasks.tasks.wadhwani_tasks.run_wadhwani_glaucoma_batch_task",
        job_token,
        list(task_ids),
        user_id=user_id,
    )
    return job_token


def enqueue_wadhwani_for_encounter_ids(
    encounter_ids: list[int] | tuple[int, ...],
    *,
    user_id: int | None = None,
    username: str | None = None,
    remote_addr: str | None = None,
) -> dict[str, Any]:
    queued = 0
    job_tokens: list[str] = []
    with transaction_scope() as db:
        encounters = (
            db.query(PatientEncounters)
            .options(
                selectinload(PatientEncounters.encounter_set_images),
                selectinload(PatientEncounters.encounter_set_attachments),
            )
            .filter(PatientEncounters.id.in_(set(encounter_ids)))
            .all()
        )
        rows = []
        for encounter in encounters:
            task_ids = create_wadhwani_task_ids_for_encounter(db, encounter)
            if task_ids:
                rows.append((encounter.id, encounter.lab_unit_id, encounter.project_id, encounter.upload_profile_id, task_ids))
        db.flush()
    for _encounter_id, lab_unit_id, project_id, upload_profile_id, task_ids in rows:
        job_token = enqueue_wadhwani_for_task_ids(
            task_ids,
            user_id=user_id,
            username=username,
            remote_addr=remote_addr,
            lab_unit_id=lab_unit_id,
            project_id=project_id,
            upload_profile_id=upload_profile_id,
        )
        if job_token:
            queued += len(task_ids)
            job_tokens.append(job_token)
    return {"wadhwani_tasks_queued": queued, "wadhwani_job_tokens": job_tokens}


def encounter_ids_from_ingest_result(result: dict[str, Any]) -> list[int]:
    encounter_ids: set[int] = set()
    for exam in result.get("exams") or []:
        if not isinstance(exam, dict):
            continue
        encounter_id = exam.get("patient_encounter_id")
        if encounter_id:
            encounter_ids.add(int(encounter_id))
        for image in exam.get("images") or []:
            if isinstance(image, dict) and image.get("patient_encounter_id"):
                encounter_ids.add(int(image["patient_encounter_id"]))
        for report in exam.get("reports") or []:
            if isinstance(report, dict) and report.get("patient_encounter_id"):
                encounter_ids.add(int(report["patient_encounter_id"]))
    return sorted(encounter_ids)


def encounter_set_report_evidence(encounter: PatientEncounters) -> set[str]:
    evidence: set[str] = set()
    for attachment in encounter.encounter_set_attachments or []:
        metadata = attachment.metadata_json or {}
        report_type = str(metadata.get("remidio_report_type") or attachment.asset_kind or "").lower()
        ocr = metadata.get("ocr") if isinstance(metadata.get("ocr"), dict) else {}
        if "dr" in report_type or isinstance(ocr.get("dr_report"), dict):
            evidence.add("dr")
        if "glaucoma" in report_type or isinstance(ocr.get("glaucoma_report"), dict):
            evidence.add("glaucoma_report")
            evidence.add("glaucoma")
    if any(_is_disc_focused_encounter_set_image(image) for image in encounter.encounter_set_images or []):
        evidence.add("glaucoma_disc_image")
        evidence.add("glaucoma")
    return evidence


def _is_disc_focused_encounter_set_image(image) -> bool:
    if getattr(image, "asset_kind", None) != "clinical_image":
        return False
    metadata = image.metadata_json or {}
    if not isinstance(metadata, dict):
        return False
    text_values = [
        metadata.get("fundus_field"),
        metadata.get("field"),
        metadata.get("focus"),
        metadata.get("centering"),
        metadata.get("image_segment"),
        metadata.get("segment"),
        metadata.get("image_type"),
        metadata.get("type"),
        metadata.get("image_variant"),
    ]
    for value in text_values:
        normalized = _normalize_disc_focus_text(value)
        if not normalized:
            continue
        tokens = set(normalized.split())
        if normalized in DISC_FOCUSED_IMAGE_TERMS:
            return True
        if tokens.intersection({"disc", "disk", "onh"}):
            return True
        if any(term in normalized for term in ("optic disc", "optic disk", "optic nerve head")):
            return True
    return False


def _normalize_disc_focus_text(value: Any) -> str:
    if value is None:
        return ""
    normalized = str(value).strip().lower()
    return normalized.replace("_", " ").replace("-", " ")


def ai_workflow_policy_applies(policy: str | None, evidence: set[str]) -> bool:
    if policy == "remidio_glaucoma_report_present":
        return "glaucoma" in evidence
    if policy == "never":
        return False
    return True


def _ai_workflow_task_scope(policy: str | None, evidence: set[str]) -> str | None:
    if policy == "never":
        return None
    if policy != "remidio_glaucoma_report_present":
        return "all"
    if "glaucoma_report" in evidence:
        return "all"
    if "glaucoma_disc_image" in evidence:
        return "disc"
    return None
