"""Configuration, candidate listing, and jobs for encounter-scoped inference."""
from __future__ import annotations

import json
from typing import Any, Iterable
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from db_transaction_manager import transaction_scope
from job_store import db_create_job
from models import AIModelIntegration, Job, JobItem, PatientEncounters, Project
from remote_inference.dr_dme_service import PROVIDER, WORKFLOW_KEY, evaluate_encounter, workflow_allows_automatic
from remote_inference.dr_dme import CandidateFilters, MAX_MANUAL_ENCOUNTERS, list_candidates, validate_selection_count
from remote_inference.models import (
    EncounterAIImageResult,
    EncounterAIInferenceRun,
    EncounterAIOutputTarget,
    EncounterAITargetResult,
    ProjectEncounterAIWorkflow,
)
from remote_inference.automated_service import _project_capabilities
from upload_profiles.admin_service import MutationResult
from upload_profiles.service import manager_lab_unit_ids
from utils.celery_helpers import enqueue_task


JOB_TYPE = "encounter_set_madhunetra_dr_dme"


def is_positive_output(target_key: str, mapped_grade: str | None) -> bool:
    """Return whether a mapped DR/DME grade represents detected disease.

    Public because the field surface rolls the same grades up to patient level;
    a second copy of this rule would drift from the referral logic below.
    """
    grade = " ".join(str(mapped_grade or "").strip().lower().split())
    if not grade or grade in {"not gradable", "ungradable"}:
        return False
    if target_key == "dr":
        return grade != "no dr"
    if target_key == "dme":
        return grade not in {"no dme", "m0 no dme"}
    return False


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
    dr_target = next((target for target in targets if target.target_key == "dr"), None)
    supporting_profiles = capabilities.get((dr_target.disease_id, "encounter_set"), set()) if dr_target else set()
    if dr_target is not None and not supporting_profiles:
        blockers.append("One active project profile must support image-level DR EncounterSet tasks.")
    automatic_blockers = list(blockers)
    return {
        "workflow_key": WORKFLOW_KEY,
        "execution_scope": "encounter",
        "provider": PROVIDER,
        "ai_model_id": integration.ai_model_id if integration else None,
        "ai_model_name": integration.ai_model.name if integration and integration.ai_model else None,
        "ai_model_version": integration.ai_model.version if integration and integration.ai_model else None,
        "automatic_enabled": bool(workflow and workflow.active and workflow.automatic_enabled),
        "manual_enabled": bool(workflow and workflow.active and workflow.manual_enabled),
        "automatic_eligibility": workflow.automatic_eligibility if workflow else "always",
        "image_selection": "macula_focused_images",
        "maximum_images_per_eye": 10,
        "output_targets": [row.target_key for row in targets],
        "supporting_profiles": sorted(supporting_profiles),
        "supporting_profile_names": sorted(supporting_profiles),
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


def resolve_enabled(payload: dict[str, Any], current: bool) -> bool:
    """Decide the new is_enabled from a possibly partial payload.

    An absent key means "not specified" and keeps the current value. Collapsing
    absence to False - the previous behaviour - meant a partial update that only
    changed the base URL silently disabled a working integration.

    The route's form branch always sends an explicit boolean, so an unchecked
    checkbox still disables.
    """
    if "is_enabled" not in payload:
        return bool(current)
    return payload["is_enabled"] is True


def resolve_environment(payload: dict[str, Any]) -> str:
    """Normalize a requested environment, or empty string when unspecified.

    Never defaults to staging: doing so let a partial update flip a production
    integration to staging without anyone asking for it.
    """
    return str(payload.get("environment") or "").strip().lower()


def _path_segments(path: str) -> list[str]:
    return [segment for segment in (path or "").split("/") if segment]


def save_integration(payload: dict[str, Any]) -> MutationResult:
    """Update endpoint/token without ever returning or logging the secret."""
    api_base_url = str(payload.get("api_base_url") or "").strip().rstrip("/")
    environment = resolve_environment(payload)
    if environment and environment not in {"staging", "production"}:
        return MutationResult(False, "Environment must be staging or production.", 400)
    parsed = urlparse(api_base_url)
    if not api_base_url or parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        return MutationResult(False, "A credential-free HTTPS API base URL is required.", 400)
    # The client appends /api/inference/... itself, so a base URL that already
    # carries that prefix produces /api/api/inference/ and every call 404s at
    # presign with no hint that the URL was doubled. Reject it at save time.
    segments = _path_segments(parsed.path)
    if segments and segments[0].lower() == "api":
        return MutationResult(
            False,
            "Enter the host only, without a /api suffix - request paths are appended automatically.",
            400,
        )
    access_token = str(payload.get("access_token") or "").strip()
    with transaction_scope() as db:
        integration = db.execute(
            select(AIModelIntegration).where(AIModelIntegration.provider == PROVIDER).with_for_update()
        ).scalar_one_or_none()
        if integration is None:
            return MutationResult(False, "MadhuNetrAI integration is not installed.", 404)
        requested_enabled = resolve_enabled(payload, integration.is_enabled)
        if requested_enabled and not (access_token or integration.access_token_encrypted):
            return MutationResult(False, "An access token is required before enabling the integration.", 400)
        integration.api_base_url = api_base_url
        if environment:
            integration.environment = environment
        if access_token:
            integration.set_access_token(access_token)
        integration.is_enabled = requested_enabled
        db.flush()
    return MutationResult(True, "MadhuNetrAI integration configuration updated.")


def list_manual_projects(
    db, user: Any, *, action: str = "project.wai.run"
) -> list[dict[str, Any]]:
    """Return scoped projects whose encounter DR-DME manual workflow is enabled."""
    query = (
        db.query(Project)
        .join(ProjectEncounterAIWorkflow, ProjectEncounterAIWorkflow.project_id == Project.id)
        .join(PatientEncounters, PatientEncounters.project_id == Project.id)
        .filter(
            ProjectEncounterAIWorkflow.workflow_key == WORKFLOW_KEY,
            ProjectEncounterAIWorkflow.active.is_(True),
            ProjectEncounterAIWorkflow.manual_enabled.is_(True),
        )
        .distinct()
        .order_by(Project.title, Project.id)
    )
    from data_authorization.policy import user_can_project_action

    return [
        {"id": row.id, "title": row.title, "code": row.code}
        for row in query.all()
        if user_can_project_action(db, user=user, project_id=row.id, action=action)
    ]


def load_job_payload(db, job_token: str) -> dict[str, Any] | None:
    """Build a non-secret encounter-level status payload for the operator UI."""
    job = db.execute(
        select(Job).where(Job.token == job_token, Job.upload_type == JOB_TYPE)
    ).scalar_one_or_none()
    if job is None:
        return None
    items = db.execute(
        select(JobItem).where(JobItem.job_id == job.id).order_by(JobItem.id)
    ).scalars().all()
    details_by_item_id: dict[int, dict[str, Any]] = {}
    for item in items:
        try:
            details_by_item_id[item.id] = json.loads(item.detail or "{}")
        except (TypeError, ValueError):
            details_by_item_id[item.id] = {}
    encounter_ids = [item.source_id for item in items if item.source_type == "patient_encounter" and item.source_id]
    encounters = db.execute(
        select(PatientEncounters).where(PatientEncounters.id.in_(encounter_ids))
    ).scalars().all() if encounter_ids else []
    encounters_by_id = {row.id: row for row in encounters}
    run_ids = {
        detail.get("run_id")
        for detail in details_by_item_id.values()
        if isinstance(detail.get("run_id"), int)
    }
    runs = db.execute(
        select(EncounterAIInferenceRun)
        .options(
            selectinload(EncounterAIInferenceRun.image_results)
            .selectinload(EncounterAIImageResult.target_results)
            .selectinload(EncounterAITargetResult.output_target)
        )
        .where(EncounterAIInferenceRun.id.in_(run_ids))
    ).scalars().all() if run_ids else []
    runs_by_id = {run.id: run for run in runs}
    summary = {
        "queued": 0,
        "processing": 0,
        "ok": 0,
        "error": 0,
        "positive_encounters": 0,
        "positive_images": 0,
    }
    rows = []
    for item in items:
        state = (item.state or "queued").lower()
        summary[state if state in summary else "queued"] += 1
        detail = details_by_item_id[item.id]
        encounter = encounters_by_id.get(item.source_id)
        run = runs_by_id.get(detail.get("run_id"))
        outputs = []
        if run is not None:
            for image_result in sorted(
                run.image_results,
                key=lambda row: (row.submitted_eye, not row.is_primary, row.id),
            ):
                grades = {
                    result.output_target.target_key: result.mapped_grade
                    for result in image_result.target_results
                    if result.output_target is not None
                }
                if grades:
                    is_positive = any(
                        is_positive_output(target_key, mapped_grade)
                        for target_key, mapped_grade in grades.items()
                    )
                    outputs.append(
                        {
                            "eye": image_result.submitted_eye,
                            "is_primary": image_result.is_primary,
                            "quality_state": image_result.quality_state,
                            "dr_grade": grades.get("dr"),
                            "dme_grade": grades.get("dme"),
                            "is_positive": is_positive,
                        }
                    )
        positive_images = sum(output["is_positive"] for output in outputs)
        summary["positive_images"] += positive_images
        if positive_images:
            summary["positive_encounters"] += 1
        rows.append(
            {
                "encounter_id": item.source_id,
                "encounter_uuid": item.source_uuid or (encounter.uuid if encounter else None),
                "patient_id": encounter.patient_id if encounter else None,
                "capture_date": encounter.capture_date_dt or encounter.capture_date if encounter else None,
                "state": state,
                "message": detail.get("message"),
                "error_code": detail.get("error_code"),
                "error_detail": detail.get("detail"),
                "request_id": detail.get("request_id"),
                "report_id": detail.get("report_id"),
                "run_id": detail.get("run_id"),
                "screening_status": detail.get("status"),
                "reused": bool(detail.get("reused")),
                "outputs": outputs,
            }
        )
    return {
        "token": job.token,
        "status": job.status,
        "error": job.error,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "items": rows,
        "summary": summary,
        "done": str(job.status or "").lower() in {"done", "error", "partial"},
    }


def create_manual_job(
    *,
    encounter_ids: Iterable[int],
    project_id: int,
    user: Any,
    remote_addr: str | None,
) -> MutationResult:
    selected_ids = list(dict.fromkeys(int(value) for value in encounter_ids))
    count_error = validate_selection_count(len(selected_ids))
    if count_error:
        return MutationResult(False, count_error, 400)
    with transaction_scope() as db:
        from data_authorization.policy import ACTION_WAI_RUN, user_can_project_action

        if not user_can_project_action(
            db, user=user, project_id=project_id, action=ACTION_WAI_RUN
        ):
            return MutationResult(False, "You cannot run WAI inference for this project.", 403)
        candidate_page = list_candidates(
            db,
            filters=CandidateFilters(
                project_id=project_id,
                encounter_ids=tuple(selected_ids),
                include_prior=True,
                page_size=MAX_MANUAL_ENCOUNTERS,
            ),
            user=user,
        )
        candidates = {row["encounter_id"]: row for row in candidate_page.rows}
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
        encounter_uuid_by_id = {row.id: row.uuid for row in encounters}
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
        for item, encounter_id in zip(job.items, selected_ids, strict=True):
            item.source_type = "patient_encounter"
            item.source_id = encounter_id
            item.source_uuid = encounter_uuid_by_id[encounter_id]
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
