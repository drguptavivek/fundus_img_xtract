"""Project-owned automated remote inference configuration."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from db_transaction_manager import transaction_scope
from models import AIModel, AIModelDisease, AIModelIntegration, Disease, Project
from remote_inference.models import DiseaseReportLinkage, ProjectAutomatedRemoteInferenceRule
from upload_profiles.admin_service import MutationResult
from upload_profiles.models import (
    ProjectUploadProfile,
    UploadProfile,
    UploadProfileEncounterSetType,
    UploadProfileEncounterSetTypeGradingPackage,
)
from upload_profiles.service import manager_lab_unit_ids

UPLOAD_KINDS = {"direct_image", "pregraded", "remidio", "encounter_set"}
EXECUTABLE_UPLOAD_KINDS = {"direct_image", "encounter_set"}
WADHWANI_PROVIDER = "wadhwani_glaucoma"
TRIGGER_TIMINGS = {"on_image_received", "on_report_received", "after_verification"}
ENCOUNTER_ELIGIBILITIES = {"always", "if_matching_report_present", "if_matching_report_absent", "if_any_report_present"}
IMAGE_SELECTIONS = {"all_eligible_images", "disc_focused_images", "macula_focused_images", "disc_or_macula_images"}


@dataclass(frozen=True)
class AutomatedRemoteInferenceRuleInput:
    disease_id: int
    ai_model_id: int
    upload_kind: str
    trigger_timing: str = "on_image_received"
    encounter_eligibility: str = "always"
    image_selection: str = "all_eligible_images"


@dataclass(frozen=True)
class AutomatedRemoteInferenceOption:
    disease_id: int
    disease_name: str
    ai_model_id: int
    ai_model_name: str
    ai_model_version: str
    provider: str
    upload_kind: str
    supporting_profiles: tuple[str, ...]
    enabled: bool
    trigger_timing: str
    encounter_eligibility: str
    image_selection: str


def _project_capabilities(db, project_id: int) -> dict[tuple[int, str], set[str]]:
    """Return disease/upload-kind capabilities derived from active project profiles."""
    mappings = (
        db.execute(
            select(ProjectUploadProfile)
            .join(UploadProfile, UploadProfile.id == ProjectUploadProfile.upload_profile_id)
            .where(
                ProjectUploadProfile.project_id == project_id,
                ProjectUploadProfile.active.is_(True),
                UploadProfile.active.is_(True),
            )
            .options(
                selectinload(ProjectUploadProfile.profile).selectinload(UploadProfile.upload_kinds),
                selectinload(ProjectUploadProfile.profile).selectinload(UploadProfile.diseases),
                selectinload(ProjectUploadProfile.profile)
                .selectinload(UploadProfile.encounter_set_types)
                .selectinload(UploadProfileEncounterSetType.image_grading_schemes),
                selectinload(ProjectUploadProfile.profile)
                .selectinload(UploadProfile.encounter_set_types)
                .selectinload(UploadProfileEncounterSetType.grading_packages)
                .selectinload(UploadProfileEncounterSetTypeGradingPackage.image_grading_schemes),
            )
        )
        .scalars()
        .unique()
        .all()
    )
    capabilities: dict[tuple[int, str], set[str]] = {}
    for mapping in mappings:
        profile = mapping.profile
        kinds = {row.upload_kind for row in profile.upload_kinds}
        for kind in (kinds & EXECUTABLE_UPLOAD_KINDS) - {"encounter_set"}:
            for disease_link in profile.diseases:
                capabilities.setdefault((disease_link.disease_id, kind), set()).add(profile.name)
        if "encounter_set" in kinds:
            disease_ids: set[int] = set()
            for config in profile.encounter_set_types:
                if not config.active:
                    continue
                disease_ids.update(row.disease_id for row in config.image_grading_schemes if row.active)
                for package in config.grading_packages:
                    if package.active and package.applicability != "disabled":
                        disease_ids.update(row.disease_id for row in package.image_grading_schemes if row.active)
            for disease_id in disease_ids:
                capabilities.setdefault((disease_id, "encounter_set"), set()).add(profile.name)
    return capabilities


def project_automated_workflow_context(db, project_id: int) -> dict[str, Any]:
    capabilities = _project_capabilities(db, project_id)
    rules = {
        (row.disease_id, row.ai_model_id, row.upload_kind): row
        for row in db.execute(
            select(ProjectAutomatedRemoteInferenceRule).where(
                ProjectAutomatedRemoteInferenceRule.project_id == project_id
            )
        ).scalars().all()
    }
    pairs = (
        db.execute(
            select(AIModelDisease)
            .join(AIModel, AIModel.id == AIModelDisease.ai_model_id)
            .join(AIModelIntegration, AIModelIntegration.ai_model_id == AIModel.id)
            .join(Disease, Disease.id == AIModelDisease.disease_id)
            .where(
                AIModelDisease.active.is_(True),
                AIModelIntegration.is_enabled.is_(True),
                AIModelIntegration.provider == WADHWANI_PROVIDER,
            )
            .options(
                selectinload(AIModelDisease.ai_model).selectinload(AIModel.integration),
                selectinload(AIModelDisease.disease),
            )
            .order_by(Disease.name, AIModel.name, AIModel.version)
        ).scalars().unique().all()
    )
    options: list[AutomatedRemoteInferenceOption] = []
    for pair in pairs:
        for (disease_id, upload_kind), profile_names in capabilities.items():
            if disease_id != pair.disease_id:
                continue
            rule = rules.get((disease_id, pair.ai_model_id, upload_kind))
            options.append(
                AutomatedRemoteInferenceOption(
                    disease_id=disease_id,
                    disease_name=pair.disease.name,
                    ai_model_id=pair.ai_model_id,
                    ai_model_name=pair.ai_model.name,
                    ai_model_version=pair.ai_model.version,
                    provider=pair.ai_model.integration.provider,
                    upload_kind=upload_kind,
                    supporting_profiles=tuple(sorted(profile_names)),
                    enabled=bool(rule and rule.active),
                    trigger_timing=rule.trigger_timing if rule else "on_image_received",
                    encounter_eligibility=rule.encounter_eligibility if rule else "always",
                    image_selection=rule.image_selection if rule else "all_eligible_images",
                )
            )
    options.sort(key=lambda row: (row.disease_name, row.ai_model_name, row.upload_kind))
    return {
        "automated_remote_inference_workflows": options,
        "automated_remote_inference_enabled": any(row.enabled for row in options),
    }


def set_project_automated_rules(
    manager_user_id: int,
    project_id: int,
    selected_rules: Iterable[AutomatedRemoteInferenceRuleInput],
) -> MutationResult:
    if not manager_lab_unit_ids(manager_user_id):
        return MutationResult(False, "You are not assigned to any lab units for remote inference management.", 403)
    selected = list(selected_rules)
    keys = {(row.disease_id, row.ai_model_id, row.upload_kind) for row in selected}
    if len(keys) != len(selected):
        return MutationResult(False, "Each automated workflow can be selected only once.", 400)
    with transaction_scope() as db:
        if db.get(Project, project_id) is None:
            return MutationResult(False, "Project not found.", 404)
        capabilities = _project_capabilities(db, project_id)
        for row in selected:
            error = _validate_rule(db, row, capabilities)
            if error:
                return MutationResult(False, error, 400)
        existing = {
            (row.disease_id, row.ai_model_id, row.upload_kind): row
            for row in db.execute(
                select(ProjectAutomatedRemoteInferenceRule).where(
                    ProjectAutomatedRemoteInferenceRule.project_id == project_id
                )
            ).scalars().all()
        }
        for key, rule in existing.items():
            rule.active = key in keys
        for order, item in enumerate(selected, start=1):
            key = (item.disease_id, item.ai_model_id, item.upload_kind)
            rule = existing.get(key)
            if rule is None:
                rule = ProjectAutomatedRemoteInferenceRule(
                    project_id=project_id,
                    disease_id=item.disease_id,
                    ai_model_id=item.ai_model_id,
                    upload_kind=item.upload_kind,
                )
                db.add(rule)
            rule.trigger_timing = item.trigger_timing
            rule.encounter_eligibility = item.encounter_eligibility
            rule.image_selection = item.image_selection
            rule.display_order = order
            rule.active = True
        try:
            db.flush()
            return MutationResult(True, "Automated remote inference workflows updated.", payload={"project_id": project_id, "enabled_workflow_count": len(keys)})
        except IntegrityError:
            db.rollback()
            return MutationResult(False, "Duplicate or invalid automated remote inference configuration.", 400)


def _validate_rule(db, rule: AutomatedRemoteInferenceRuleInput, capabilities: dict[tuple[int, str], set[str]]) -> str | None:
    if rule.upload_kind not in UPLOAD_KINDS or (rule.disease_id, rule.upload_kind) not in capabilities:
        return "The selected upload kind and disease are not supported by an active profile for this project."
    if rule.trigger_timing not in TRIGGER_TIMINGS:
        return "Unsupported automated inference trigger timing."
    if rule.encounter_eligibility not in ENCOUNTER_ELIGIBILITIES:
        return "Unsupported encounter eligibility policy."
    if rule.image_selection not in IMAGE_SELECTIONS:
        return "Unsupported image selection policy."
    if rule.encounter_eligibility in {"if_matching_report_present", "if_matching_report_absent"}:
        if db.execute(select(DiseaseReportLinkage.id).where(DiseaseReportLinkage.disease_id == rule.disease_id, DiseaseReportLinkage.active.is_(True))).first() is None:
            return "Matching-report eligibility requires an explicit disease/report linkage."
    if db.execute(
        select(AIModelDisease.id)
        .join(AIModelIntegration, AIModelIntegration.ai_model_id == AIModelDisease.ai_model_id)
        .where(
            AIModelDisease.disease_id == rule.disease_id,
            AIModelDisease.ai_model_id == rule.ai_model_id,
            AIModelDisease.active.is_(True),
            AIModelIntegration.is_enabled.is_(True),
        )
    ).first() is None:
        return "AI model must be enabled and linked to the selected disease."
    return None


def rule_inputs_from_values(values: Iterable[Any]) -> list[AutomatedRemoteInferenceRuleInput]:
    rules: list[AutomatedRemoteInferenceRuleInput] = []
    for value in values:
        if isinstance(value, dict):
            try:
                rules.append(AutomatedRemoteInferenceRuleInput(
                    disease_id=int(value["disease_id"]), ai_model_id=int(value["ai_model_id"]),
                    upload_kind=str(value["upload_kind"]),
                    trigger_timing=str(value.get("trigger_timing") or "on_image_received"),
                    encounter_eligibility=str(value.get("encounter_eligibility") or "always"),
                    image_selection=str(value.get("image_selection") or "all_eligible_images"),
                ))
            except (KeyError, TypeError, ValueError):
                continue
            continue
        parts = str(value or "").split(":")
        if len(parts) < 3:
            continue
        try:
            rules.append(AutomatedRemoteInferenceRuleInput(
                disease_id=int(parts[0]), ai_model_id=int(parts[1]), upload_kind=parts[2],
                trigger_timing=parts[3] if len(parts) > 3 else "on_image_received",
                encounter_eligibility=parts[4] if len(parts) > 4 else "always",
                image_selection=parts[5] if len(parts) > 5 else "all_eligible_images",
            ))
        except (TypeError, ValueError):
            continue
    return rules


def active_rule(db, *, project_id: int, disease_id: int, ai_model_id: int | None = None, upload_kind: str) -> ProjectAutomatedRemoteInferenceRule | None:
    query = select(ProjectAutomatedRemoteInferenceRule).where(
        ProjectAutomatedRemoteInferenceRule.project_id == project_id,
        ProjectAutomatedRemoteInferenceRule.disease_id == disease_id,
        ProjectAutomatedRemoteInferenceRule.upload_kind == upload_kind,
        ProjectAutomatedRemoteInferenceRule.active.is_(True),
    ).order_by(ProjectAutomatedRemoteInferenceRule.display_order, ProjectAutomatedRemoteInferenceRule.id)
    if ai_model_id is not None:
        query = query.where(ProjectAutomatedRemoteInferenceRule.ai_model_id == ai_model_id)
    return db.execute(query).scalars().first()
