"""Configuration, candidate listing, and jobs for encounter-scoped inference."""
from __future__ import annotations

from typing import Any, Iterable
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from db_transaction_manager import transaction_scope
from job_store import db_create_job
from models import AIModelIntegration, Job, JobItem, PatientEncounters, Project
from remote_inference.dr_dme_service import PROVIDER, WORKFLOW_KEY, evaluate_encounter, workflow_allows_automatic
from remote_inference.models import EncounterAIInferenceRun, EncounterAIOutputTarget, ProjectEncounterAIWorkflow
from remote_inference.automated_service import _project_capabilities
from remidio_api_integration.models import ProjectUploadProfileRemidioApiBinding
from upload_profiles.models import ProjectUploadProfile
from upload_profiles.admin_service import MutationResult
from upload_profiles.service import manager_lab_unit_ids
from utils.celery_helpers import enqueue_task
from utils.hospital_scoping import apply_scoping


MAX_MANUAL_ENCOUNTERS = 25
JOB_TYPE = "encounter_set_madhunetra_dr_dme"


def workflow_context(db, project_id: int) -> dict[str, Any]:
    integration = db.execute(
        select(AIModelIntegration).where(AIModelIntegration.provider == PROVIDER)
    ).scalar_one_or_none()
    workflow = db.execute(
        select(ProjectEncounterAIWorkflow).where(
            ProjectEncounterAIWorkflow.project_id == project_id,
            ProjectEncounterAIWorkflow.workflow_key == WORKFLOW_KEY,
        )
    ).scalar_one_or_none()
    targets = []
    if integration:
        targets = db.execute(
            select(EncounterAIOutputTarget).where(
                EncounterAIOutputTarget.ai_model_id == integration.ai_model_id,
                EncounterAIOutputTarget.active.is_(True),
            )
        ).scalars().all()
    blockers: list[str] = []
    if integration is None:
        blockers.append("Model integration has not been installed.")
    elif not integration.is_enabled:
        blockers.append("Model integration is disabled.")
    elif not integration.api_base_url or not integration.access_token_encrypted:
        blockers.append("Endpoint and encrypted access token are required.")
    if {row.target_key for row in targets} != {"dr", "dme"}:
        blockers.append("Active DR and DME output mappings are required.")
    capabilities = _project_capabilities(db, project_id)
    supporting_profile_sets = [
        capabilities.get((target.disease_id, "encounter_set"), set()) for target in targets
    ]
    common_profiles = set.intersection(*supporting_profile_sets) if supporting_profile_sets else set()
    if len(targets) == 2 and not common_profiles:
        blockers.append("One active project profile must support image-level DR and DME EncounterSet tasks.")
    automatic_blockers = list(blockers)
    has_remidio_binding = db.execute(
        select(ProjectUploadProfileRemidioApiBinding.id)
        .join(ProjectUploadProfile, ProjectUploadProfile.id == ProjectUploadProfileRemidioApiBinding.project_upload_profile_id)
        .where(
            ProjectUploadProfile.project_id == project_id,
            ProjectUploadProfile.active.is_(True),
            ProjectUploadProfileRemidioApiBinding.active.is_(True),
        )
    ).first() is not None
    if not has_remidio_binding:
        automatic_blockers.append("Automatic execution requires an active prospective Remidio API binding.")
    return {
        "workflow_key": WORKFLOW_KEY,
        "execution_scope": "encounter",
        "provider": PROVIDER,
        "ai_model_id": integration.ai_model_id if integration else None,
        "automatic_enabled": bool(workflow and workflow.active and workflow.automatic_enabled),
        "manual_enabled": bool(workflow and workflow.active and workflow.manual_enabled),
        "automatic_eligibility": workflow.automatic_eligibility if workflow else "always",
        "image_selection": "macula_focused_images",
        "maximum_images_per_eye": 10,
        "output_targets": [row.target_key for row in targets],
        "supporting_profiles": sorted(common_profiles),
        "manual_capable": not blockers,
        "automatic_capable": not automatic_blockers,
        "capable": not blockers,
        "blocking_reasons": blockers,
        "automatic_blocking_reasons": automatic_blockers,
    }


def save_workflow(manager_user_id: int, project_id: int, payload: dict[str, Any]) -> MutationResult:
    if not manager_lab_unit_ids(manager_user_id):
        return MutationResult(False, "You are not assigned to any lab units for remote inference management.", 403)
    eligibility = str(payload.get("automatic_eligibility") or "always")
    if eligibility not in {"always", "if_dr_ocr_report_present"}:
        return MutationResult(False, "Unsupported automatic eligibility policy.", 400)
    with transaction_scope() as db:
        if db.get(Project, project_id) is None:
            return MutationResult(False, "Project not found.", 404)
        context = workflow_context(db, project_id)
        if payload.get("manual_enabled") and not context["manual_capable"]:
            return MutationResult(False, "; ".join(context["blocking_reasons"]), 409)
        if payload.get("automatic_enabled") and not context["automatic_capable"]:
            return MutationResult(False, "; ".join(context["automatic_blocking_reasons"]), 409)
        integration = db.execute(
            select(AIModelIntegration).where(AIModelIntegration.provider == PROVIDER)
        ).scalar_one_or_none()
        if integration is None:
            return MutationResult(False, "Model integration has not been installed.", 409)
        workflow = db.execute(
            select(ProjectEncounterAIWorkflow).where(
                ProjectEncounterAIWorkflow.project_id == project_id,
                ProjectEncounterAIWorkflow.workflow_key == WORKFLOW_KEY,
            )
        ).scalar_one_or_none()
        if workflow is None:
            workflow = ProjectEncounterAIWorkflow(project_id=project_id, ai_model_id=integration.ai_model_id)
            db.add(workflow)
        workflow.ai_model_id = integration.ai_model_id
        workflow.automatic_enabled = payload.get("automatic_enabled") is True
        workflow.manual_enabled = payload.get("manual_enabled") is True
        workflow.automatic_eligibility = eligibility
        workflow.active = True
        db.flush()
    return MutationResult(True, "Encounter remote inference workflow updated.", payload={"project_id": project_id})


def integration_context(db) -> dict[str, Any] | None:
    integration = db.execute(
        select(AIModelIntegration).where(AIModelIntegration.provider == PROVIDER)
    ).scalar_one_or_none()
    if integration is None:
        return None
    return {
        "provider": integration.provider,
        "ai_model_id": integration.ai_model_id,
        "is_enabled": integration.is_enabled,
        "api_base_url": integration.api_base_url,
        "environment": integration.environment,
        "has_access_token": bool(integration.access_token_encrypted),
        "config": integration.config_json or {},
    }


def save_integration(payload: dict[str, Any]) -> MutationResult:
    """Update endpoint/token without ever returning or logging the secret."""
    api_base_url = str(payload.get("api_base_url") or "").strip().rstrip("/")
    environment = str(payload.get("environment") or "staging").strip().lower()
    if environment not in {"staging", "production"}:
        return MutationResult(False, "Environment must be staging or production.", 400)
    parsed = urlparse(api_base_url)
    if not api_base_url or parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        return MutationResult(False, "A credential-free HTTPS API base URL is required.", 400)
    access_token = str(payload.get("access_token") or "").strip()
    with transaction_scope() as db:
        integration = db.execute(
            select(AIModelIntegration).where(AIModelIntegration.provider == PROVIDER).with_for_update()
        ).scalar_one_or_none()
        if integration is None:
            return MutationResult(False, "MadhuNetrAI integration is not installed.", 404)
        requested_enabled = payload.get("is_enabled") is True
        if requested_enabled and not (access_token or integration.access_token_encrypted):
            return MutationResult(False, "An access token is required before enabling the integration.", 400)
        integration.api_base_url = api_base_url
        integration.environment = environment
        if access_token:
            integration.set_access_token(access_token)
        integration.is_enabled = requested_enabled
        db.flush()
    return MutationResult(True, "MadhuNetrAI integration configuration updated.")


def list_candidates(db, *, project_id: int, user: Any) -> list[dict[str, Any]]:
    workflow = db.execute(
        select(ProjectEncounterAIWorkflow).where(
            ProjectEncounterAIWorkflow.project_id == project_id,
            ProjectEncounterAIWorkflow.workflow_key == WORKFLOW_KEY,
            ProjectEncounterAIWorkflow.active.is_(True),
            ProjectEncounterAIWorkflow.manual_enabled.is_(True),
        )
    ).scalar_one_or_none()
    if workflow is None:
        return []
    query = (
        db.query(PatientEncounters)
        .options(selectinload(PatientEncounters.encounter_set_images))
        .filter(
            PatientEncounters.project_id == project_id,
            PatientEncounters.is_set_based.is_(True),
        )
        .order_by(PatientEncounters.capture_date_dt.desc(), PatientEncounters.id.desc())
    )
    encounters = apply_scoping(query, PatientEncounters, user, "upload").limit(100).all()
    run_by_encounter = {
        row.patient_encounter_id: row
        for row in db.execute(
            select(EncounterAIInferenceRun).where(
                EncounterAIInferenceRun.patient_encounter_id.in_([encounter.id for encounter in encounters]),
                EncounterAIInferenceRun.ai_model_id == workflow.ai_model_id,
            )
        ).scalars().all()
    } if encounters else {}
    rows = []
    for encounter in encounters:
        eligibility = evaluate_encounter(encounter, require_verified=True)
        run = run_by_encounter.get(encounter.id)
        rows.append(
            {
                "encounter_id": encounter.id,
                "encounter_uuid": encounter.uuid,
                "patient_id": encounter.patient_id,
                "capture_date": encounter.capture_date_dt.isoformat() if encounter.capture_date_dt else encounter.capture_date,
                "eligible": eligibility.eligible,
                "eligibility_issues": list(eligibility.issues),
                "eye_counts": eligibility.eye_counts,
                "run_status": run.status if run else "not_requested",
                "report_id": run.report_id if run else None,
            }
        )
    return rows


def create_manual_job(
    *,
    encounter_ids: Iterable[int],
    project_id: int,
    user: Any,
    remote_addr: str | None,
) -> MutationResult:
    selected_ids = list(dict.fromkeys(int(value) for value in encounter_ids))
    if not selected_ids or len(selected_ids) > MAX_MANUAL_ENCOUNTERS:
        return MutationResult(False, "Select between 1 and 25 EncounterSets.", 400)
    with transaction_scope() as db:
        candidates = {row["encounter_id"]: row for row in list_candidates(db, project_id=project_id, user=user)}
        selected = [candidates.get(encounter_id) for encounter_id in selected_ids]
        if any(row is None for row in selected):
            return MutationResult(False, "One or more EncounterSets are outside your authorized project/lab scope.", 403)
        ineligible = [row for row in selected if not row["eligible"]]
        if ineligible:
            return MutationResult(False, "Every selected EncounterSet must be verified and eligible.", 409)
        encounters = db.execute(
            select(PatientEncounters).where(PatientEncounters.id.in_(selected_ids))
        ).scalars().all()
        lab_ids = {row.lab_unit_id for row in encounters}
        lab_unit_id = next(iter(lab_ids)) if len(lab_ids) == 1 else None
    token = db_create_job(
        [f"encounter:{encounter_id}" for encounter_id in selected_ids],
        [],
        uploader_user_id=user.id,
        uploader_username=user.username,
        uploader_ip=remote_addr,
        lab_unit_id=lab_unit_id,
        project_id=project_id,
        upload_type=JOB_TYPE,
        upload_kind="encounter_set",
    )
    with transaction_scope() as db:
        job = db.execute(select(Job).options(selectinload(Job.items)).where(Job.token == token)).scalar_one()
        by_id = {row.id: row for row in encounters}
        for item, encounter_id in zip(job.items, selected_ids, strict=True):
            item.source_type = "patient_encounter"
            item.source_id = encounter_id
            item.source_uuid = by_id[encounter_id].uuid
            item.task_id = None
    enqueue_task(
        "celery_tasks.tasks.wadhwani_tasks.run_madhunetra_dr_dme_batch_task",
        token,
        selected_ids,
        user_id=user.id,
    )
    return MutationResult(True, f"Queued {len(selected_ids)} EncounterSet(s) for DR-DME screening.", payload={"job_token": token}, status_code=202)


def enqueue_automatic_encounters(encounter_ids: Iterable[int], *, user_id: int | None = None) -> dict[str, Any]:
    """Evaluate complete API-ingested encounters and queue configured screenings."""
    queued: list[int] = []
    with transaction_scope() as db:
        encounters = db.execute(
            select(PatientEncounters)
            .options(
                selectinload(PatientEncounters.encounter_set_images),
                selectinload(PatientEncounters.encounter_set_attachments),
            )
            .where(PatientEncounters.id.in_(set(encounter_ids)))
        ).scalars().all()
        for encounter in encounters:
            workflow = db.execute(
                select(ProjectEncounterAIWorkflow).where(
                    ProjectEncounterAIWorkflow.project_id == encounter.project_id,
                    ProjectEncounterAIWorkflow.workflow_key == WORKFLOW_KEY,
                    ProjectEncounterAIWorkflow.active.is_(True),
                )
            ).scalar_one_or_none()
            if workflow is None or not workflow_allows_automatic(workflow, encounter):
                continue
            if not evaluate_encounter(encounter, require_verified=False).eligible:
                continue
            prior = db.execute(
                select(EncounterAIInferenceRun.id).where(
                    EncounterAIInferenceRun.patient_encounter_id == encounter.id,
                    EncounterAIInferenceRun.ai_model_id == workflow.ai_model_id,
                    EncounterAIInferenceRun.status.in_(("queued", "presigning", "uploading", "submitting", "success", "partial")),
                )
            ).first()
            if prior is None:
                queued_job = db.execute(
                    select(JobItem.id)
                    .join(Job, Job.id == JobItem.job_id)
                    .where(
                        Job.upload_type == JOB_TYPE,
                        Job.status.in_(("queued", "processing")),
                        JobItem.source_type == "patient_encounter",
                        JobItem.source_id == encounter.id,
                        JobItem.state.in_(("queued", "processing")),
                    )
                ).first()
                if queued_job is None:
                    queued.append(encounter.id)
    tokens = []
    for encounter_id in queued:
        with transaction_scope() as db:
            encounter = db.get(PatientEncounters, encounter_id)
            token = db_create_job(
                [f"encounter:{encounter_id}"],
                [],
                uploader_user_id=user_id,
                lab_unit_id=encounter.lab_unit_id,
                project_id=encounter.project_id,
                upload_type=JOB_TYPE,
                upload_kind="encounter_set",
                upload_profile_id=encounter.upload_profile_id,
            )
            encounter_uuid = encounter.uuid
        with transaction_scope() as db:
            job = db.execute(select(Job).options(selectinload(Job.items)).where(Job.token == token)).scalar_one()
            item = job.items[0]
            item.source_type = "patient_encounter"
            item.source_id = encounter_id
            item.source_uuid = encounter_uuid
        enqueue_task(
            "celery_tasks.tasks.wadhwani_tasks.run_madhunetra_dr_dme_batch_task",
            token,
            [encounter_id],
            user_id=user_id,
            source="automatic",
        )
        tokens.append(token)
    return {"madhunetra_encounters_queued": len(tokens), "madhunetra_job_tokens": tokens}
