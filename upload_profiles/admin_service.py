"""Admin-facing upload profile service."""
from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from db_transaction_manager import transaction_scope
from encounter_set_types.models import EncounterSetType
from models import AIModel, AIModelDisease, Disease, LabUnit, Project, ProjectInvestigator, User
from upload_profiles.models import (
    ProjectUploadProfile,
    ProjectUploadProfileAssignment,
    UploadProfile,
    UploadProfileAIWorkflow,
    UploadProfileArea,
    UploadProfileCamera,
    UploadProfileDisease,
    UploadProfileEncounterSetType,
    UploadProfileEncounterSetTypeImageGradingScheme,
    UploadProfileKind,
)
from upload_profiles.service import (
    UPLOAD_KIND_DIRECT_IMAGE,
    UPLOAD_KIND_ENCOUNTER_SET,
    UPLOAD_KIND_PREGRADED,
    UPLOAD_KIND_REMIDIO,
    manager_lab_unit_ids,
)


@dataclass(frozen=True)
class MutationResult:
    success: bool
    message: str
    status_code: int = 200
    payload: dict[str, Any] | None = None


@dataclass(frozen=True)
class ProjectCreateInput:
    title: str
    code: str
    description: str | None = None


@dataclass(frozen=True)
class InvestigatorCreateInput:
    project_id: int | None
    user_id: int | None
    role: str


@dataclass(frozen=True)
class AIWorkflowInput:
    disease_id: int
    ai_model_id: int
    upload_kind: str


@dataclass(frozen=True)
class EncounterSetProfileInput:
    encounter_set_type_id: int
    image_grading_scheme_ids: list[int]
    default_image_grading_scheme_id: int | None
    encounter_grading_scheme_id: int | None


@dataclass(frozen=True)
class UploadProfileInput:
    name: str
    disease_ids: list[int]
    default_disease_ids: list[int]
    camera_ids: list[int]
    area_ids: list[int]
    upload_kinds: list[str]
    allow_mydriatic: bool
    allow_non_mydriatic: bool
    default_is_mydriatic: bool
    automated_remidio_populated: bool
    ai_workflows: list[AIWorkflowInput]
    encounter_set_configs: list[EncounterSetProfileInput]
    task_prioritization_json: dict[str, Any] | None = None
    description: str | None = None


@dataclass(frozen=True)
class ProjectProfileInput:
    project_id: int | None
    upload_profile_id: int | None


@dataclass(frozen=True)
class ProjectProfileAssignmentInput:
    project_upload_profile_id: int | None
    user_id: int | None
    lab_unit_ids: list[int]


@dataclass(frozen=True)
class ProjectProfileAssignmentRemoveInput:
    assignment_id: int | None


def to_int(value: str | None) -> int | None:
    try:
        return int(value) if value else None
    except (TypeError, ValueError):
        return None


def to_int_list(values: list[str]) -> list[int]:
    parsed: list[int] = []
    for value in values:
        item = to_int(value)
        if item is not None:
            parsed.append(item)
    return parsed


def validate_mydriatic_flags(*, allow_mydriatic: bool, allow_non_mydriatic: bool, default_is_mydriatic: bool) -> str | None:
    if not allow_mydriatic and not allow_non_mydriatic:
        return "Select at least one mydriatic scope."
    if default_is_mydriatic and not allow_mydriatic:
        return "Default cannot be mydriatic unless mydriatic uploads are allowed."
    if not default_is_mydriatic and not allow_non_mydriatic:
        return "Default cannot be non-mydriatic unless non-mydriatic uploads are allowed."
    return None


def create_project(project_input: ProjectCreateInput) -> MutationResult:
    if not project_input.title or not project_input.code:
        return MutationResult(False, "Project title and code are required.", 400)
    with transaction_scope() as db:
        try:
            project = Project(title=project_input.title, code=project_input.code, description=project_input.description, active=True)
            db.add(project)
            db.flush()
            return MutationResult(True, "Project created.", payload={"project_id": project.id})
        except IntegrityError:
            db.rollback()
            return MutationResult(False, "Duplicate or invalid project configuration.", 400)


def update_project(project_id: int, project_input: ProjectCreateInput) -> MutationResult:
    if not project_input.title or not project_input.code:
        return MutationResult(False, "Project title and code are required.", 400)
    with transaction_scope() as db:
        project = db.get(Project, project_id)
        if not project:
            return MutationResult(False, "Project not found.", 404)
        try:
            project.title = project_input.title
            project.code = project_input.code
            project.description = project_input.description
            db.flush()
            return MutationResult(True, "Project updated.", payload={"project_id": project.id})
        except IntegrityError:
            db.rollback()
            return MutationResult(False, "Duplicate or invalid project configuration.", 400)


def add_investigator(investigator_input: InvestigatorCreateInput) -> MutationResult:
    if not investigator_input.project_id or not investigator_input.user_id:
        return MutationResult(False, "Project and investigator are required.", 400)
    with transaction_scope() as db:
        try:
            investigator = ProjectInvestigator(
                project_id=investigator_input.project_id,
                user_id=investigator_input.user_id,
                role=investigator_input.role,
                active=True,
            )
            db.add(investigator)
            db.flush()
            return MutationResult(True, "Project investigator added.", payload={"investigator_id": investigator.id})
        except IntegrityError:
            db.rollback()
            return MutationResult(False, "Duplicate or invalid project investigator configuration.", 400)


def enable_project_profile(manager_user_id: int, profile_input: ProjectProfileInput) -> MutationResult:
    if not profile_input.project_id or not profile_input.upload_profile_id:
        return MutationResult(False, "Project and upload profile are required.", 400)
    if not manager_lab_unit_ids(manager_user_id):
        return MutationResult(False, "You are not assigned to any lab units for upload profile management.", 403)
    with transaction_scope() as db:
        project = db.get(Project, profile_input.project_id)
        profile = db.get(UploadProfile, profile_input.upload_profile_id)
        if not project or not profile:
            return MutationResult(False, "Project or upload profile not found.", 404)
        mapping = (
            db.execute(
                select(ProjectUploadProfile).where(
                    ProjectUploadProfile.project_id == project.id,
                    ProjectUploadProfile.upload_profile_id == profile.id,
                )
            )
            .scalars()
            .one_or_none()
        )
        if mapping:
            mapping.active = True
        else:
            mapping = ProjectUploadProfile(project_id=project.id, upload_profile_id=profile.id, active=True)
            db.add(mapping)
        try:
            db.flush()
            return MutationResult(True, "Upload profile enabled for project.", payload={"project_upload_profile_id": mapping.id})
        except IntegrityError:
            db.rollback()
            return MutationResult(False, "Duplicate or invalid project upload profile mapping.", 400)


def set_project_profile_active(manager_user_id: int, project_upload_profile_id: int, active: bool) -> MutationResult:
    if not manager_lab_unit_ids(manager_user_id):
        return MutationResult(False, "You are not assigned to any lab units for upload profile management.", 403)
    with transaction_scope() as db:
        mapping = db.get(ProjectUploadProfile, project_upload_profile_id)
        if not mapping:
            return MutationResult(False, "Project upload profile mapping not found.", 404)
        mapping.active = active
        return MutationResult(
            True,
            "Upload profile enabled for project." if active else "Upload profile disabled for project.",
            payload={"project_upload_profile_id": mapping.id},
        )


def assign_project_profile_user(manager_user_id: int, assignment_input: ProjectProfileAssignmentInput) -> MutationResult:
    if not assignment_input.project_upload_profile_id or not assignment_input.user_id or not assignment_input.lab_unit_ids:
        return MutationResult(False, "Project profile, user, and lab unit are required.", 400)
    scoped_lab_ids = manager_lab_unit_ids(manager_user_id)
    requested_lab_ids = set(assignment_input.lab_unit_ids)
    if not requested_lab_ids.issubset(scoped_lab_ids):
        return MutationResult(False, "You cannot assign upload access outside your lab-unit scope.", 403)
    with transaction_scope() as db:
        project_profile = db.get(ProjectUploadProfile, assignment_input.project_upload_profile_id)
        if not project_profile or not project_profile.active:
            return MutationResult(False, "Project upload profile mapping not found or inactive.", 404)
        if project_profile.profile and project_profile.profile.automated_remidio_populated:
            return MutationResult(False, "Automated Remidio API profiles do not use uploader assignments.", 400)
        lab_error = _validate_user_lab_assignment(db, assignment_input.user_id, requested_lab_ids)
        if lab_error:
            return MutationResult(False, lab_error, 400)
        last_assignment: ProjectUploadProfileAssignment | None = None
        for lab_unit_id in sorted(requested_lab_ids):
            assignment = (
                db.execute(
                    select(ProjectUploadProfileAssignment).where(
                        ProjectUploadProfileAssignment.project_upload_profile_id == project_profile.id,
                        ProjectUploadProfileAssignment.user_id == assignment_input.user_id,
                        ProjectUploadProfileAssignment.lab_unit_id == lab_unit_id,
                    )
                )
                .scalars()
                .one_or_none()
            )
            if assignment:
                assignment.active = True
            else:
                assignment = ProjectUploadProfileAssignment(
                    project_upload_profile_id=project_profile.id,
                    user_id=assignment_input.user_id,
                    lab_unit_id=lab_unit_id,
                    active=True,
                )
                db.add(assignment)
            last_assignment = assignment
        try:
            db.flush()
            return MutationResult(
                True,
                "User assigned to project upload profile.",
                payload={"assignment_id": last_assignment.id if last_assignment else None},
            )
        except IntegrityError:
            db.rollback()
            return MutationResult(False, "Duplicate or invalid project upload profile assignment.", 400)


def remove_project_profile_assignment(manager_user_id: int, assignment_input: ProjectProfileAssignmentRemoveInput) -> MutationResult:
    if not assignment_input.assignment_id:
        return MutationResult(False, "Assignment is required.", 400)
    scoped_lab_ids = manager_lab_unit_ids(manager_user_id)
    with transaction_scope() as db:
        assignment = db.get(ProjectUploadProfileAssignment, assignment_input.assignment_id)
        if not assignment or assignment.lab_unit_id not in scoped_lab_ids:
            return MutationResult(False, "Project upload profile assignment not found in your lab-unit scope.", 404)
        assignment.active = False
        return MutationResult(True, "User removed from project upload profile.", payload={"assignment_id": assignment.id})


def create_profile(manager_user_id: int, profile_input: UploadProfileInput) -> MutationResult:
    if not manager_lab_unit_ids(manager_user_id):
        return MutationResult(False, "You are not assigned to any lab units for upload profile management.", 403)
    profile = UploadProfile(active=True)
    with transaction_scope() as db:
        try:
            validation_error = _apply_profile_input(db, profile, profile_input)
            if validation_error:
                return MutationResult(False, validation_error, 400)
            db.add(profile)
            db.flush()
            return MutationResult(True, "Upload profile created.", payload={"profile_id": profile.id})
        except IntegrityError:
            db.rollback()
            return MutationResult(False, "Duplicate or invalid upload profile configuration.", 400)


def update_profile(manager_user_id: int, profile_id: int, profile_input: UploadProfileInput) -> MutationResult:
    if not manager_lab_unit_ids(manager_user_id):
        return MutationResult(False, "You are not assigned to any lab units for upload profile management.", 403)
    with transaction_scope() as db:
        profile = db.get(UploadProfile, profile_id)
        if not profile:
            return MutationResult(False, "Upload profile not found.", 404)
        try:
            validation_error = _apply_profile_input(db, profile, profile_input)
            if validation_error:
                return MutationResult(False, validation_error, 400)
            return MutationResult(True, "Upload profile updated.", payload={"profile_id": profile.id})
        except IntegrityError:
            db.rollback()
            return MutationResult(False, "Duplicate or invalid upload profile configuration.", 400)


def duplicate_profile(manager_user_id: int, profile_id: int) -> MutationResult:
    if not manager_lab_unit_ids(manager_user_id):
        return MutationResult(False, "You are not assigned to any lab units for upload profile management.", 403)
    with transaction_scope() as db:
        source = db.get(UploadProfile, profile_id)
        if not source:
            return MutationResult(False, "Upload profile not found.", 404)
        duplicate = UploadProfile(
            name=f"{source.name} Copy",
            description=source.description,
            task_prioritization_json=source.task_prioritization_json,
            allow_mydriatic=source.allow_mydriatic,
            allow_non_mydriatic=source.allow_non_mydriatic,
            default_is_mydriatic=source.default_is_mydriatic,
            automated_remidio_populated=source.automated_remidio_populated,
            active=True,
        )
        duplicate.diseases = [UploadProfileDisease(disease_id=row.disease_id, is_default=row.is_default) for row in source.diseases]
        duplicate.cameras = [UploadProfileCamera(camera_id=row.camera_id) for row in source.cameras]
        duplicate.areas = [UploadProfileArea(area_id=row.area_id) for row in source.areas]
        duplicate.upload_kinds = [UploadProfileKind(upload_kind=row.upload_kind) for row in source.upload_kinds]
        duplicate.encounter_set_types = [
            UploadProfileEncounterSetType(
                encounter_set_type_id=row.encounter_set_type_id,
                encounter_grading_scheme_id=row.encounter_grading_scheme_id,
                default_image_grading_scheme_id=row.default_image_grading_scheme_id,
                active=row.active,
                image_grading_schemes=[
                    UploadProfileEncounterSetTypeImageGradingScheme(
                        disease_id=scheme.disease_id,
                        is_default=scheme.is_default,
                        display_order=scheme.display_order,
                        active=scheme.active,
                    )
                    for scheme in row.image_grading_schemes
                    if scheme.active
                ],
            )
            for row in source.encounter_set_types
            if row.active
        ]
        db.add(duplicate)
        try:
            db.flush()
            return MutationResult(True, "Upload profile duplicated.", payload={"profile_id": duplicate.id})
        except IntegrityError:
            db.rollback()
            return MutationResult(False, "Duplicate or invalid upload profile configuration.", 400)


def set_profile_active(manager_user_id: int, profile_id: int, active: bool) -> MutationResult:
    if not manager_lab_unit_ids(manager_user_id):
        return MutationResult(False, "You are not assigned to any lab units for upload profile management.", 403)
    with transaction_scope() as db:
        profile = db.get(UploadProfile, profile_id)
        if not profile:
            return MutationResult(False, "Upload profile not found.", 404)
        profile.active = active
        return MutationResult(True, "Upload profile activated." if active else "Upload profile deactivated.", payload={"profile_id": profile.id})


def _apply_profile_input(db, profile: UploadProfile, profile_input: UploadProfileInput) -> str | None:
    if not profile_input.name:
        return "Profile name is required."

    if not profile_input.upload_kinds:
        return "Select at least one upload type."
    upload_kinds = sorted(set(profile_input.upload_kinds))
    if not set(upload_kinds).issubset({UPLOAD_KIND_DIRECT_IMAGE, UPLOAD_KIND_PREGRADED, UPLOAD_KIND_REMIDIO, UPLOAD_KIND_ENCOUNTER_SET}):
        return "Unsupported upload type selected."
    if profile_input.automated_remidio_populated and set(upload_kinds) != {UPLOAD_KIND_ENCOUNTER_SET}:
        return "Automated Remidio API profiles must allow only EncounterSet uploads."
    disease_required_kinds = {UPLOAD_KIND_DIRECT_IMAGE, UPLOAD_KIND_PREGRADED, UPLOAD_KIND_REMIDIO}
    clinical_upload_enabled = bool(set(upload_kinds).intersection(disease_required_kinds))
    if clinical_upload_enabled and not profile_input.disease_ids:
        return "Allowed diseases are required for direct image, pregraded, and Remidio ZIP uploads."
    if clinical_upload_enabled and (not profile_input.camera_ids or not profile_input.area_ids):
        return "Cameras and sites are required for direct image, pregraded, and Remidio ZIP uploads."
    if clinical_upload_enabled:
        mydriatic_error = validate_mydriatic_flags(
            allow_mydriatic=profile_input.allow_mydriatic,
            allow_non_mydriatic=profile_input.allow_non_mydriatic,
            default_is_mydriatic=profile_input.default_is_mydriatic,
        )
        if mydriatic_error:
            return mydriatic_error
    elif profile_input.disease_ids:
        return "Allowed diseases are only used for direct image, pregraded, and Remidio ZIP uploads."
    default_ids = set(profile_input.default_disease_ids)
    disease_ids = set(profile_input.disease_ids)
    if default_ids and not default_ids.issubset(disease_ids):
        return "Default diseases must be included in allowed diseases."
    if UPLOAD_KIND_REMIDIO in upload_kinds and not default_ids:
        return "Select a default disease for Remidio ZIP ingestion."
    if UPLOAD_KIND_REMIDIO not in upload_kinds and default_ids:
        return "Default disease is only used for Remedio ZIP profiles."
    encounter_set_configs = _normalize_encounter_set_configs(profile_input.encounter_set_configs)
    if UPLOAD_KIND_ENCOUNTER_SET in upload_kinds and not encounter_set_configs:
        return "Select at least one EncounterSetType for encounter-set uploads."
    if UPLOAD_KIND_ENCOUNTER_SET not in upload_kinds and encounter_set_configs:
        return "EncounterSetTypes are only used when encounter-set uploads are allowed."
    encounter_set_error = _validate_encounter_set_configs(db, encounter_set_configs)
    if encounter_set_error:
        return encounter_set_error
    if profile_input.automated_remidio_populated:
        remidio_type_ids = {
            row_id
            for row_id in db.execute(
                select(EncounterSetType.id).where(
                    EncounterSetType.id.in_(encounter_set_configs.keys()),
                    EncounterSetType.code == "remidio_api_standard",
                    EncounterSetType.active.is_(True),
                )
            ).scalars().all()
        }
        if not remidio_type_ids:
            return "Automated Remidio API profiles must include the Remidio API Standard EncounterSetType."
    prioritization_result = normalize_task_prioritization(profile_input.task_prioritization_json, set(upload_kinds))
    if not prioritization_result.success:
        return prioritization_result.message
    ai_workflows = _valid_ai_workflows(db, profile_input.ai_workflows, disease_ids, set(upload_kinds))
    if ai_workflows is None:
        return "AI workflow disease and upload type must be included in the profile, and AI models must exist."

    profile.name = profile_input.name
    profile.description = profile_input.description
    profile.automated_remidio_populated = profile_input.automated_remidio_populated
    profile.task_prioritization_json = prioritization_result.payload["task_prioritization_json"]
    profile.allow_mydriatic = profile_input.allow_mydriatic if clinical_upload_enabled else False
    profile.allow_non_mydriatic = profile_input.allow_non_mydriatic if clinical_upload_enabled else True
    profile.default_is_mydriatic = profile_input.default_is_mydriatic if clinical_upload_enabled else False

    if profile.id is not None:
        _clear_profile_children(db, profile)

    profile.diseases = [
        UploadProfileDisease(disease_id=disease_id, is_default=disease_id in default_ids)
        for disease_id in sorted(disease_ids)
    ]
    profile.cameras = [
        UploadProfileCamera(camera_id=camera_id)
        for camera_id in sorted(set(profile_input.camera_ids if clinical_upload_enabled else []))
    ]
    profile.areas = [
        UploadProfileArea(area_id=area_id)
        for area_id in sorted(set(profile_input.area_ids if clinical_upload_enabled else []))
    ]
    profile.upload_kinds = [UploadProfileKind(upload_kind=upload_kind) for upload_kind in upload_kinds]
    profile.encounter_set_types = [
        UploadProfileEncounterSetType(
            encounter_set_type_id=config.encounter_set_type_id,
            encounter_grading_scheme_id=config.encounter_grading_scheme_id,
            default_image_grading_scheme_id=config.default_image_grading_scheme_id,
            active=True,
            image_grading_schemes=[
                UploadProfileEncounterSetTypeImageGradingScheme(
                    disease_id=disease_id,
                    is_default=disease_id == config.default_image_grading_scheme_id,
                    display_order=index,
                    active=True,
                )
                for index, disease_id in enumerate(config.image_grading_scheme_ids, start=1)
            ],
        )
        for config in sorted(encounter_set_configs.values(), key=lambda item: item.encounter_set_type_id)
    ]
    profile.ai_workflows = [
        UploadProfileAIWorkflow(
            disease_id=workflow.disease_id,
            ai_model_id=workflow.ai_model_id,
            upload_kind=workflow.upload_kind,
            active=True,
        )
        for workflow in ai_workflows
    ]
    return None


def _normalize_encounter_set_configs(configs: list[EncounterSetProfileInput]) -> dict[int, EncounterSetProfileInput]:
    normalized: dict[int, EncounterSetProfileInput] = {}
    for config in configs:
        if not config.encounter_set_type_id:
            continue
        image_scheme_ids = sorted(set(config.image_grading_scheme_ids))
        default_image_scheme_id = config.default_image_grading_scheme_id
        if len(image_scheme_ids) == 1:
            default_image_scheme_id = image_scheme_ids[0]
        normalized[config.encounter_set_type_id] = EncounterSetProfileInput(
            encounter_set_type_id=config.encounter_set_type_id,
            image_grading_scheme_ids=image_scheme_ids,
            default_image_grading_scheme_id=default_image_scheme_id,
            encounter_grading_scheme_id=config.encounter_grading_scheme_id,
        )
    return normalized


def _validate_encounter_set_configs(db, configs: dict[int, EncounterSetProfileInput]) -> str | None:
    if not configs:
        return None
    encounter_set_type_ids = set(configs)
    valid_encounter_set_type_ids = set(
        db.execute(
            select(EncounterSetType.id).where(
                EncounterSetType.id.in_(encounter_set_type_ids),
                EncounterSetType.active.is_(True),
            )
        ).scalars().all()
    )
    if valid_encounter_set_type_ids != encounter_set_type_ids:
        return "EncounterSetTypes must be active."

    disease_ids: set[int] = set()
    for config in configs.values():
        if not config.image_grading_scheme_ids:
            return "Select at least one image grading scheme for every selected EncounterSetType."
        if not config.encounter_grading_scheme_id:
            return "Select an encounter grading scheme for every selected EncounterSetType."
        if not config.default_image_grading_scheme_id:
            return "Select a default image grading scheme for every selected EncounterSetType."
        if config.default_image_grading_scheme_id not in config.image_grading_scheme_ids:
            return "Default image grading scheme must be one of the selected image grading schemes."
        disease_ids.update(config.image_grading_scheme_ids)
        disease_ids.add(config.encounter_grading_scheme_id)

    diseases = {row.id: row for row in db.execute(select(Disease).where(Disease.id.in_(disease_ids))).scalars().all()}
    if set(diseases) != disease_ids:
        return "One or more grading schemes were not found."
    image_scope_errors = sorted(
        diseases[disease_id].name
        for config in configs.values()
        for disease_id in config.image_grading_scheme_ids
        if diseases[disease_id].grading_scope != "image"
    )
    if image_scope_errors:
        return "Image grading schemes must have image scope: " + ", ".join(image_scope_errors)
    encounter_scope_errors = sorted(
        diseases[config.encounter_grading_scheme_id].name
        for config in configs.values()
        if diseases[config.encounter_grading_scheme_id].grading_scope != "encounter"
    )
    if encounter_scope_errors:
        return "Encounter grading schemes must have encounter scope: " + ", ".join(encounter_scope_errors)
    return None


def normalize_task_prioritization(raw_config: Any, upload_kinds: set[str]) -> MutationResult:
    defaults = {
        "active": False,
        "prioritize_abnormal_encounters": False,
        "prioritize_ai_abnormal_images": False,
        "normal_sampling_percent": 100,
        "normal_sampling_strategy": "random",
        "priority_source_order": ["encounter_abnormal", "ai_abnormal"],
        "apply_to_upload_kinds": sorted(upload_kinds),
    }
    if raw_config in (None, ""):
        return MutationResult(True, "Task prioritization normalized.", payload={"task_prioritization_json": defaults})
    if isinstance(raw_config, str):
        try:
            raw_config = json.loads(raw_config)
        except json.JSONDecodeError:
            return MutationResult(False, "Task prioritization must be valid JSON.", 400)
    if not isinstance(raw_config, dict):
        return MutationResult(False, "Task prioritization must be an object.", 400)
    config = defaults | raw_config
    for key in ("active", "prioritize_abnormal_encounters", "prioritize_ai_abnormal_images"):
        config[key] = _bool_value(config.get(key))
    try:
        config["normal_sampling_percent"] = int(config.get("normal_sampling_percent", 100))
    except (TypeError, ValueError):
        return MutationResult(False, "Normal sampling percent must be between 0 and 100.", 400)
    if config["normal_sampling_percent"] < 0 or config["normal_sampling_percent"] > 100:
        return MutationResult(False, "Normal sampling percent must be between 0 and 100.", 400)
    if config.get("normal_sampling_strategy") != "random":
        return MutationResult(False, "Only random normal sampling strategy is supported now.", 400)
    source_order = config.get("priority_source_order")
    if not isinstance(source_order, list) or not all(item in {"encounter_abnormal", "ai_abnormal"} for item in source_order):
        return MutationResult(False, "Priority source order must contain encounter_abnormal and/or ai_abnormal.", 400)
    apply_kinds = config.get("apply_to_upload_kinds") or []
    if not isinstance(apply_kinds, list):
        return MutationResult(False, "Prioritization upload kinds must be a list.", 400)
    apply_kinds = sorted(set(str(item) for item in apply_kinds))
    if not set(apply_kinds).issubset(upload_kinds):
        return MutationResult(False, "Prioritization upload kinds must be enabled for the profile.", 400)
    config["apply_to_upload_kinds"] = apply_kinds
    return MutationResult(True, "Task prioritization normalized.", payload={"task_prioritization_json": config})


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _clear_profile_children(db, profile: UploadProfile) -> None:
    """Flush deleted child rows before replacement inserts hit unique constraints."""
    profile.diseases = []
    profile.cameras = []
    profile.areas = []
    profile.upload_kinds = []
    profile.encounter_set_types = []
    profile.ai_workflows = []
    db.flush()


def _validate_user_lab_assignment(db, user_id: int | None, lab_unit_ids: set[int]) -> str | None:
    if not user_id:
        return "User is required."
    user = (
        db.execute(
            select(User)
            .options(selectinload(User.lab_units))
            .where(User.id == user_id, User.is_active.is_(True))
        )
        .scalars()
        .one_or_none()
    )
    if not user:
        return "Selected user is not active."
    labs = (
        db.execute(select(LabUnit).where(LabUnit.id.in_(lab_unit_ids)))
        .scalars()
        .all()
    )
    if {lab.id for lab in labs} != lab_unit_ids:
        return "Selected lab unit was not found."
    user_lab_ids = {lab.id for lab in user.lab_units or []}
    if not lab_unit_ids.issubset(user_lab_ids):
        return "Selected user must be explicitly assigned to every selected lab unit."
    user_hospital_id = getattr(user, "hospital_id", None)
    if any(lab.hospital_id != user_hospital_id for lab in labs):
        return "Selected lab units must belong to the user's hospital."
    return None


def _valid_ai_workflows(
    db,
    workflow_inputs: list[AIWorkflowInput],
    disease_ids: set[int],
    upload_kinds: set[str],
) -> list[AIWorkflowInput] | None:
    deduped: dict[tuple[int, int, str], AIWorkflowInput] = {}
    disease_target_kinds = {UPLOAD_KIND_DIRECT_IMAGE, "pregraded", UPLOAD_KIND_REMIDIO}
    for workflow in workflow_inputs:
        if (
            workflow.disease_id not in disease_ids
            or workflow.upload_kind not in upload_kinds
            or workflow.upload_kind not in disease_target_kinds
        ):
            return None
        deduped[(workflow.disease_id, workflow.ai_model_id, workflow.upload_kind)] = workflow
    if not deduped:
        return []
    model_ids = {workflow.ai_model_id for workflow in deduped.values()}
    valid_model_ids = {row[0] for row in db.execute(select(AIModel.id).where(AIModel.id.in_(model_ids))).all()}
    if valid_model_ids != model_ids:
        return None
    valid_pairs = {
        (row[0], row[1])
        for row in db.execute(
            select(AIModelDisease.ai_model_id, AIModelDisease.disease_id).where(
                AIModelDisease.active.is_(True),
                AIModelDisease.ai_model_id.in_(model_ids),
                AIModelDisease.disease_id.in_(disease_ids),
            )
        ).all()
    }
    for workflow in deduped.values():
        if (workflow.ai_model_id, workflow.disease_id) not in valid_pairs:
            return None
    return sorted(deduped.values(), key=lambda workflow: (workflow.disease_id, workflow.ai_model_id, workflow.upload_kind))
