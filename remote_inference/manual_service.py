"""Project-owned manual remote inference configuration and authorization."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from db_transaction_manager import transaction_scope
from models import AIModel, AIModelDisease, AIModelIntegration, Disease, PatientEncounters, Project
from remote_inference.models import ProjectManualRemoteInferenceWorkflow
from upload_profiles.admin_service import MutationResult
from upload_profiles.service import manager_lab_unit_ids

WADHWANI_PROVIDER = "wadhwani_glaucoma"
ENCOUNTER_SET_UPLOAD_KIND = "encounter_set"
SUPPORTED_UPLOAD_KINDS = {"direct_image", "pregraded", "remidio", ENCOUNTER_SET_UPLOAD_KIND}


@dataclass(frozen=True)
class ManualRemoteInferenceWorkflowKey:
    disease_id: int
    ai_model_id: int
    upload_kind: str


@dataclass(frozen=True)
class ManualRemoteInferenceWorkflowOption:
    disease_id: int
    disease_name: str
    ai_model_id: int
    ai_model_name: str
    ai_model_version: str
    provider: str
    upload_kind: str
    enabled: bool


def project_manual_workflow_context(db, project_id: int) -> dict[str, Any]:
    """Return available remote workflows and project-specific manual enablement."""
    enabled_keys = {
        (row.disease_id, row.ai_model_id, row.upload_kind)
        for row in db.execute(
            select(ProjectManualRemoteInferenceWorkflow).where(
                ProjectManualRemoteInferenceWorkflow.project_id == project_id,
                ProjectManualRemoteInferenceWorkflow.active.is_(True),
            )
        )
        .scalars()
        .all()
    }
    pairs = (
        db.execute(
            select(AIModelDisease)
            .join(AIModel, AIModel.id == AIModelDisease.ai_model_id)
            .join(AIModelIntegration, AIModelIntegration.ai_model_id == AIModel.id)
            .join(Disease, Disease.id == AIModelDisease.disease_id)
            .where(
                AIModelDisease.active.is_(True),
                AIModelIntegration.provider == WADHWANI_PROVIDER,
                AIModelIntegration.is_enabled.is_(True),
                func.lower(Disease.name) == "glaucoma",
            )
            .options(selectinload(AIModelDisease.ai_model), selectinload(AIModelDisease.disease))
            .order_by(AIModel.name, AIModel.version)
        )
        .scalars()
        .unique()
        .all()
    )
    options = [
        ManualRemoteInferenceWorkflowOption(
            disease_id=pair.disease_id,
            disease_name=pair.disease.name,
            ai_model_id=pair.ai_model_id,
            ai_model_name=pair.ai_model.name,
            ai_model_version=pair.ai_model.version,
            provider=WADHWANI_PROVIDER,
            upload_kind=ENCOUNTER_SET_UPLOAD_KIND,
            enabled=(pair.disease_id, pair.ai_model_id, ENCOUNTER_SET_UPLOAD_KIND) in enabled_keys,
        )
        for pair in pairs
    ]
    return {
        "manual_remote_inference_workflows": options,
        "manual_remote_inference_enabled": any(option.enabled for option in options),
    }


def set_project_manual_workflows(
    manager_user_id: int,
    project_id: int,
    selected_workflows: Iterable[ManualRemoteInferenceWorkflowKey],
) -> MutationResult:
    """Replace active manual workflow selections while retaining historical rows."""
    if not manager_lab_unit_ids(manager_user_id):
        return MutationResult(False, "You are not assigned to any lab units for remote inference management.", 403)
    selected = list(selected_workflows)
    keys = {(row.disease_id, row.ai_model_id, row.upload_kind) for row in selected}
    if len(keys) != len(selected):
        return MutationResult(False, "Each manual remote inference workflow can be selected only once.", 400)
    if any(row.upload_kind not in SUPPORTED_UPLOAD_KINDS for row in selected):
        return MutationResult(False, "Unsupported manual remote inference upload kind.", 400)

    with transaction_scope() as db:
        project = db.get(Project, project_id)
        if not project:
            return MutationResult(False, "Project not found.", 404)
        for row in selected:
            valid_pair = db.execute(
                select(AIModelDisease.id)
                .join(AIModelIntegration, AIModelIntegration.ai_model_id == AIModelDisease.ai_model_id)
                .join(Disease, Disease.id == AIModelDisease.disease_id)
                .where(
                    AIModelDisease.disease_id == row.disease_id,
                    AIModelDisease.ai_model_id == row.ai_model_id,
                    AIModelDisease.active.is_(True),
                    AIModelIntegration.provider == WADHWANI_PROVIDER,
                    AIModelIntegration.is_enabled.is_(True),
                    func.lower(Disease.name) == "glaucoma",
                )
            ).first()
            if valid_pair is None or row.upload_kind != ENCOUNTER_SET_UPLOAD_KIND:
                return MutationResult(False, "Manual workflow must use the enabled Wadhwani glaucoma model for EncounterSets.", 400)

        existing = {
            (row.disease_id, row.ai_model_id, row.upload_kind): row
            for row in db.execute(
                select(ProjectManualRemoteInferenceWorkflow).where(
                    ProjectManualRemoteInferenceWorkflow.project_id == project_id
                )
            )
            .scalars()
            .all()
        }
        for key, mapping in existing.items():
            mapping.active = key in keys
        for row in selected:
            key = (row.disease_id, row.ai_model_id, row.upload_kind)
            if key not in existing:
                db.add(
                    ProjectManualRemoteInferenceWorkflow(
                        project_id=project_id,
                        disease_id=row.disease_id,
                        ai_model_id=row.ai_model_id,
                        upload_kind=row.upload_kind,
                        active=True,
                    )
                )
        try:
            db.flush()
            return MutationResult(
                True,
                "Manual remote inference workflows updated.",
                payload={"project_id": project_id, "enabled_workflow_count": len(keys)},
            )
        except IntegrityError:
            db.rollback()
            return MutationResult(False, "Duplicate or invalid manual remote inference configuration.", 400)


def workflow_keys_from_values(values: Iterable[str]) -> list[ManualRemoteInferenceWorkflowKey]:
    workflows: list[ManualRemoteInferenceWorkflowKey] = []
    for value in values:
        parts = str(value or "").split(":")
        if len(parts) != 3:
            continue
        try:
            disease_id = int(parts[0])
            ai_model_id = int(parts[1])
        except (TypeError, ValueError):
            continue
        if disease_id > 0 and ai_model_id > 0:
            workflows.append(
                ManualRemoteInferenceWorkflowKey(
                    disease_id=disease_id,
                    ai_model_id=ai_model_id,
                    upload_kind=parts[2],
                )
            )
    return workflows


def list_manual_wadhwani_projects(
    db, user: Any, *, action: str = "project.wai.run"
) -> list[dict[str, Any]]:
    """List active, scoped projects enabled for manual EncounterSet Wadhwani inference."""
    query = (
        db.query(Project)
        .join(ProjectManualRemoteInferenceWorkflow, ProjectManualRemoteInferenceWorkflow.project_id == Project.id)
        .join(AIModelIntegration, AIModelIntegration.ai_model_id == ProjectManualRemoteInferenceWorkflow.ai_model_id)
        .join(Disease, Disease.id == ProjectManualRemoteInferenceWorkflow.disease_id)
        .join(PatientEncounters, PatientEncounters.project_id == Project.id)
        .filter(
            Project.active.is_(True),
            ProjectManualRemoteInferenceWorkflow.active.is_(True),
            ProjectManualRemoteInferenceWorkflow.upload_kind == ENCOUNTER_SET_UPLOAD_KIND,
            AIModelIntegration.provider == WADHWANI_PROVIDER,
            AIModelIntegration.is_enabled.is_(True),
            func.lower(Disease.name) == "glaucoma",
            PatientEncounters.is_set_based.is_(True),
        )
        .order_by(Project.title.asc())
        .distinct()
    )
    from data_authorization.policy import user_can_project_action

    return [
        {"id": project.id, "title": project.title, "code": project.code}
        for project in query.all()
        if user_can_project_action(
            db, user=user, project_id=project.id, action=action
        )
    ]


def project_allows_manual_wadhwani(db, project_id: int) -> bool:
    """Return whether a project may manually submit EncounterSet images to Wadhwani."""
    return (
        db.query(ProjectManualRemoteInferenceWorkflow.id)
        .join(Project, Project.id == ProjectManualRemoteInferenceWorkflow.project_id)
        .join(AIModelIntegration, AIModelIntegration.ai_model_id == ProjectManualRemoteInferenceWorkflow.ai_model_id)
        .join(Disease, Disease.id == ProjectManualRemoteInferenceWorkflow.disease_id)
        .filter(
            ProjectManualRemoteInferenceWorkflow.project_id == project_id,
            ProjectManualRemoteInferenceWorkflow.active.is_(True),
            ProjectManualRemoteInferenceWorkflow.upload_kind == ENCOUNTER_SET_UPLOAD_KIND,
            Project.active.is_(True),
            AIModelIntegration.provider == WADHWANI_PROVIDER,
            AIModelIntegration.is_enabled.is_(True),
            func.lower(Disease.name) == "glaucoma",
        )
        .first()
        is not None
    )
