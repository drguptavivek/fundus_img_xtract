"""Admin service for remote inference policy management."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from db_transaction_manager import transaction_scope
from models import AIModel, AIModelDisease, AIModelIntegration, Disease, Project
from remote_inference.models import DiseaseReportLinkage, ProjectRemoteInferencePolicy, RemoteInferencePolicy, RemoteInferencePolicyRule
from upload_profiles.admin_service import MutationResult, to_int
from upload_profiles.service import manager_lab_unit_ids

TRIGGER_TIMINGS = {"on_image_received", "on_report_received", "after_verification", "manual_only"}
ENCOUNTER_ELIGIBILITIES = {"always", "if_matching_report_present", "if_matching_report_absent", "if_any_report_present"}
IMAGE_SELECTIONS = {"all_eligible_images", "disc_focused_images", "macula_focused_images", "disc_or_macula_images"}
UPLOAD_KINDS = {"direct_image", "pregraded", "remidio", "encounter_set"}


@dataclass(frozen=True)
class RemoteInferenceRuleInput:
    disease_id: int
    ai_model_id: int
    upload_kind: str
    trigger_timing: str
    encounter_eligibility: str
    image_selection: str


@dataclass(frozen=True)
class ProjectRemoteInferencePolicyInput:
    name: str
    description: str | None
    rules: list[RemoteInferenceRuleInput]


def remote_inference_options(db) -> dict[str, Any]:
    """Return selectable disease/model/report-linkage data for policy forms."""
    diseases = (
        db.execute(select(Disease).where(Disease.grading_scope == "image").order_by(Disease.name))
        .scalars()
        .all()
    )
    ai_models = (
        db.execute(
            select(AIModel)
            .join(AIModelIntegration, AIModelIntegration.ai_model_id == AIModel.id)
            .where(AIModelIntegration.is_enabled.is_(True))
            .options(selectinload(AIModel.integration), selectinload(AIModel.disease_links))
            .order_by(AIModel.name, AIModel.version)
        )
        .scalars()
        .unique()
        .all()
    )
    report_linkages = (
        db.execute(select(DiseaseReportLinkage).where(DiseaseReportLinkage.active.is_(True)))
        .scalars()
        .all()
    )
    return {
        "remote_inference_diseases": diseases,
        "remote_inference_ai_models": ai_models,
        "remote_inference_report_linkages": report_linkages,
    }


def project_policy_context(db, project_id: int) -> dict[str, Any]:
    assignment = (
        db.execute(
            select(ProjectRemoteInferencePolicy)
            .where(ProjectRemoteInferencePolicy.project_id == project_id, ProjectRemoteInferencePolicy.active.is_(True))
            .options(
                selectinload(ProjectRemoteInferencePolicy.policy)
                .selectinload(RemoteInferencePolicy.rules)
                .selectinload(RemoteInferencePolicyRule.disease),
                selectinload(ProjectRemoteInferencePolicy.policy)
                .selectinload(RemoteInferencePolicy.rules)
                .selectinload(RemoteInferencePolicyRule.ai_model),
            )
        )
        .scalars()
        .first()
    )
    return {"remote_inference_assignment": assignment, "remote_inference_policy": assignment.policy if assignment else None}


def save_project_policy(
    manager_user_id: int,
    project_id: int,
    policy_input: ProjectRemoteInferencePolicyInput,
) -> MutationResult:
    if not manager_lab_unit_ids(manager_user_id):
        return MutationResult(False, "You are not assigned to any lab units for remote inference policy management.", 403)
    if not policy_input.name:
        return MutationResult(False, "Remote inference policy name is required.", 400)
    with transaction_scope() as db:
        project = db.get(Project, project_id)
        if not project:
            return MutationResult(False, "Project not found.", 404)
        error = _validate_rules(db, policy_input.rules)
        if error:
            return MutationResult(False, error, 400)
        assignment = (
            db.execute(select(ProjectRemoteInferencePolicy).where(ProjectRemoteInferencePolicy.project_id == project_id))
            .scalars()
            .one_or_none()
        )
        if assignment and assignment.policy:
            policy = assignment.policy
            policy.name = policy_input.name
            policy.description = policy_input.description
            policy.active = True
            assignment.active = True
        else:
            policy = RemoteInferencePolicy(name=policy_input.name, description=policy_input.description, active=True)
            db.add(policy)
            db.flush()
            assignment = ProjectRemoteInferencePolicy(project_id=project_id, remote_inference_policy_id=policy.id, active=True)
            db.add(assignment)
        policy.rules = [
            RemoteInferencePolicyRule(
                disease_id=rule.disease_id,
                ai_model_id=rule.ai_model_id,
                upload_kind=rule.upload_kind,
                trigger_timing=rule.trigger_timing,
                encounter_eligibility=rule.encounter_eligibility,
                image_selection=rule.image_selection,
                display_order=index,
                active=True,
            )
            for index, rule in enumerate(policy_input.rules, start=1)
        ]
        try:
            db.flush()
            return MutationResult(True, "Remote inference policy saved.", payload={"remote_inference_policy_id": policy.id})
        except IntegrityError:
            db.rollback()
            return MutationResult(False, "Duplicate or invalid remote inference policy configuration.", 400)


def _validate_rules(db, rules: list[RemoteInferenceRuleInput]) -> str | None:
    seen: set[tuple[int, int, str]] = set()
    for rule in rules:
        key = (rule.disease_id, rule.ai_model_id, rule.upload_kind)
        if key in seen:
            return "Each disease, AI model, and upload kind can appear only once in a remote inference policy."
        seen.add(key)
        if rule.upload_kind not in UPLOAD_KINDS:
            return "Unsupported remote inference upload kind."
        if rule.trigger_timing not in TRIGGER_TIMINGS:
            return "Unsupported remote inference trigger timing."
        if rule.encounter_eligibility not in ENCOUNTER_ELIGIBILITIES:
            return "Unsupported encounter eligibility policy."
        if rule.image_selection not in IMAGE_SELECTIONS:
            return "Unsupported image selection policy."
        if rule.encounter_eligibility in {"if_matching_report_present", "if_matching_report_absent"}:
            linkage = (
                db.execute(
                    select(DiseaseReportLinkage.id).where(
                        DiseaseReportLinkage.disease_id == rule.disease_id,
                        DiseaseReportLinkage.active.is_(True),
                    )
                )
                .first()
            )
            if linkage is None:
                return "Matching-report eligibility requires an explicit disease/report linkage."
        pair = (
            db.execute(
                select(AIModelDisease.id)
                .join(AIModelIntegration, AIModelIntegration.ai_model_id == AIModelDisease.ai_model_id)
                .where(
                    AIModelDisease.ai_model_id == rule.ai_model_id,
                    AIModelDisease.disease_id == rule.disease_id,
                    AIModelDisease.active.is_(True),
                    AIModelIntegration.is_enabled.is_(True),
                )
            )
            .first()
        )
        if pair is None:
            return "AI model must be enabled and explicitly linked to the selected disease."
    return None


def policy_input_from_form(form) -> ProjectRemoteInferencePolicyInput:
    rules: list[RemoteInferenceRuleInput] = []
    for token in form.getlist("remote_inference_rule"):
        parts = str(token or "").split(":")
        if len(parts) != 2:
            continue
        disease_id = to_int(parts[0])
        ai_model_id = to_int(parts[1])
        if not disease_id or not ai_model_id:
            continue
        prefix = f"remote_rule_{disease_id}_{ai_model_id}"
        rules.append(
            RemoteInferenceRuleInput(
                disease_id=disease_id,
                ai_model_id=ai_model_id,
                upload_kind=form.get(f"{prefix}_upload_kind") or "encounter_set",
                trigger_timing=form.get(f"{prefix}_trigger_timing") or "on_image_received",
                encounter_eligibility=form.get(f"{prefix}_encounter_eligibility") or "always",
                image_selection=form.get(f"{prefix}_image_selection") or "all_eligible_images",
            )
        )
    return ProjectRemoteInferencePolicyInput(
        name=(form.get("remote_inference_policy_name") or "").strip(),
        description=(form.get("remote_inference_policy_description") or "").strip() or None,
        rules=rules,
    )
