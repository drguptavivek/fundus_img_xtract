"""Admin-facing upload profile service."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from db_transaction_manager import transaction_scope
from encounter_set_types.models import EncounterSetType
from models import AIModel, AIModelDisease, Project, ProjectInvestigator, user_lab_units
from upload_profiles.models import (
    UploadProfile,
    UploadProfileAIWorkflow,
    UploadProfileArea,
    UploadProfileAssignment,
    UploadProfileCamera,
    UploadProfileDisease,
    UploadProfileEncounterSetType,
    UploadProfileKind,
)
from upload_profiles.service import UPLOAD_KIND_DIRECT_IMAGE, UPLOAD_KIND_ENCOUNTER_SET, UPLOAD_KIND_REMIDIO, manager_lab_unit_ids


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
class ProfileAssignmentInput:
    profile_id: int | None
    user_id: int | None


@dataclass(frozen=True)
class AIWorkflowInput:
    disease_id: int
    ai_model_id: int
    upload_kind: str


@dataclass(frozen=True)
class UploadProfileInput:
    name: str
    lab_unit_id: int | None
    project_id: int | None
    disease_ids: list[int]
    default_disease_ids: list[int]
    camera_ids: list[int]
    area_ids: list[int]
    upload_kinds: list[str]
    allow_mydriatic: bool
    allow_non_mydriatic: bool
    default_is_mydriatic: bool
    ai_workflows: list[AIWorkflowInput]
    encounter_set_type_ids: list[int]
    description: str | None = None
    user_ids: list[int] | None = None


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


def assign_profile_user(manager_user_id: int, assignment_input: ProfileAssignmentInput) -> MutationResult:
    if not assignment_input.profile_id or not assignment_input.user_id:
        return MutationResult(False, "Upload profile and user are required.", 400)
    scoped_lab_ids = manager_lab_unit_ids(manager_user_id)
    with transaction_scope() as db:
        profile = db.get(UploadProfile, assignment_input.profile_id)
        if not profile or profile.lab_unit_id not in scoped_lab_ids:
            return MutationResult(False, "Upload profile not found in your lab-unit scope.", 404)
        if not _user_has_lab_unit(db, assignment_input.user_id, profile.lab_unit_id):
            return MutationResult(False, "Selected user must be assigned to the profile lab unit.", 400)
        assignment = (
            db.execute(
                select(UploadProfileAssignment).where(
                    UploadProfileAssignment.upload_profile_id == profile.id,
                    UploadProfileAssignment.user_id == assignment_input.user_id,
                )
            )
            .scalars()
            .one_or_none()
        )
        if assignment:
            assignment.active = True
        else:
            assignment = UploadProfileAssignment(
                upload_profile_id=profile.id,
                user_id=assignment_input.user_id,
                active=True,
            )
            db.add(assignment)
        try:
            db.flush()
            return MutationResult(True, "User assigned to upload profile.", payload={"assignment_id": assignment.id})
        except IntegrityError:
            db.rollback()
            return MutationResult(False, "Duplicate or invalid upload profile assignment.", 400)


def remove_profile_user(manager_user_id: int, assignment_input: ProfileAssignmentInput) -> MutationResult:
    if not assignment_input.profile_id or not assignment_input.user_id:
        return MutationResult(False, "Upload profile and user are required.", 400)
    scoped_lab_ids = manager_lab_unit_ids(manager_user_id)
    with transaction_scope() as db:
        profile = db.get(UploadProfile, assignment_input.profile_id)
        if not profile or profile.lab_unit_id not in scoped_lab_ids:
            return MutationResult(False, "Upload profile not found in your lab-unit scope.", 404)
        assignment = (
            db.execute(
                select(UploadProfileAssignment).where(
                    UploadProfileAssignment.upload_profile_id == profile.id,
                    UploadProfileAssignment.user_id == assignment_input.user_id,
                )
            )
            .scalars()
            .one_or_none()
        )
        if not assignment:
            return MutationResult(False, "Upload profile assignment not found.", 404)
        assignment.active = False
        return MutationResult(True, "User removed from upload profile.", payload={"assignment_id": assignment.id})


def create_profile(manager_user_id: int, profile_input: UploadProfileInput) -> MutationResult:
    scoped_lab_ids = manager_lab_unit_ids(manager_user_id)
    profile = UploadProfile(active=True)
    with transaction_scope() as db:
        try:
            validation_error = _apply_profile_input(db, profile, scoped_lab_ids, profile_input)
            if validation_error:
                return MutationResult(False, validation_error, 400)
            db.add(profile)
            db.flush()
            return MutationResult(True, "Upload profile created.", payload={"profile_id": profile.id})
        except IntegrityError:
            db.rollback()
            return MutationResult(False, "Duplicate or invalid upload profile configuration.", 400)


def update_profile(manager_user_id: int, profile_id: int, profile_input: UploadProfileInput) -> MutationResult:
    scoped_lab_ids = manager_lab_unit_ids(manager_user_id)
    with transaction_scope() as db:
        profile = db.get(UploadProfile, profile_id)
        if not profile or profile.lab_unit_id not in scoped_lab_ids:
            return MutationResult(False, "Upload profile not found in your lab-unit scope.", 404)
        try:
            validation_error = _apply_profile_input(db, profile, scoped_lab_ids, profile_input)
            if validation_error:
                return MutationResult(False, validation_error, 400)
            return MutationResult(True, "Upload profile updated.", payload={"profile_id": profile.id})
        except IntegrityError:
            db.rollback()
            return MutationResult(False, "Duplicate or invalid upload profile configuration.", 400)


def duplicate_profile(manager_user_id: int, profile_id: int) -> MutationResult:
    scoped_lab_ids = manager_lab_unit_ids(manager_user_id)
    with transaction_scope() as db:
        source = db.get(UploadProfile, profile_id)
        if not source or source.lab_unit_id not in scoped_lab_ids:
            return MutationResult(False, "Upload profile not found in your lab-unit scope.", 404)
        duplicate = UploadProfile(
            name=f"{source.name} Copy",
            description=source.description,
            lab_unit_id=source.lab_unit_id,
            project_id=source.project_id,
            allow_mydriatic=source.allow_mydriatic,
            allow_non_mydriatic=source.allow_non_mydriatic,
            default_is_mydriatic=source.default_is_mydriatic,
            active=True,
        )
        duplicate.diseases = [UploadProfileDisease(disease_id=row.disease_id, is_default=row.is_default) for row in source.diseases]
        duplicate.cameras = [UploadProfileCamera(camera_id=row.camera_id) for row in source.cameras]
        duplicate.areas = [UploadProfileArea(area_id=row.area_id) for row in source.areas]
        duplicate.upload_kinds = [UploadProfileKind(upload_kind=row.upload_kind) for row in source.upload_kinds]
        duplicate.encounter_set_types = [
            UploadProfileEncounterSetType(encounter_set_type_id=row.encounter_set_type_id, active=row.active)
            for row in source.encounter_set_types
            if row.active
        ]
        db.add(duplicate)
        try:
            db.flush()
            return MutationResult(True, "Upload profile duplicated.", payload={"profile_id": duplicate.id})
        except IntegrityError:
            db.rollback()
            return MutationResult(False, "Duplicate profile name already exists for this project and lab unit.", 400)


def set_profile_active(manager_user_id: int, profile_id: int, active: bool) -> MutationResult:
    scoped_lab_ids = manager_lab_unit_ids(manager_user_id)
    with transaction_scope() as db:
        profile = db.get(UploadProfile, profile_id)
        if not profile or profile.lab_unit_id not in scoped_lab_ids:
            return MutationResult(False, "Upload profile not found in your lab-unit scope.", 404)
        profile.active = active
        return MutationResult(True, "Upload profile activated." if active else "Upload profile deactivated.", payload={"profile_id": profile.id})


def _apply_profile_input(db, profile: UploadProfile, scoped_lab_ids: set[int], profile_input: UploadProfileInput) -> str | None:
    if (
        not profile_input.name
        or not profile_input.lab_unit_id
        or not profile_input.project_id
        or not profile_input.disease_ids
        or not profile_input.camera_ids
        or not profile_input.area_ids
    ):
        return "Profile name, lab unit, project, diseases, cameras, and sites are required."
    if profile_input.lab_unit_id not in scoped_lab_ids:
        return "You cannot manage upload profiles outside your assigned lab units."
    mydriatic_error = validate_mydriatic_flags(
        allow_mydriatic=profile_input.allow_mydriatic,
        allow_non_mydriatic=profile_input.allow_non_mydriatic,
        default_is_mydriatic=profile_input.default_is_mydriatic,
    )
    if mydriatic_error:
        return mydriatic_error

    valid_user_ids: set[int] | None = None
    if profile_input.user_ids is not None:
        requested_user_ids = set(profile_input.user_ids)
        if requested_user_ids:
            valid_user_ids = {
                row[0]
                for row in db.execute(
                    select(user_lab_units.c.user_id).where(
                        user_lab_units.c.lab_unit_id == profile_input.lab_unit_id,
                        user_lab_units.c.user_id.in_(requested_user_ids),
                    )
                ).all()
            }
        else:
            valid_user_ids = set()
        if valid_user_ids != requested_user_ids:
            return "All selected uploaders must be assigned to the profile lab unit."

    upload_kinds = sorted(set(profile_input.upload_kinds or [UPLOAD_KIND_DIRECT_IMAGE]))
    default_ids = set(profile_input.default_disease_ids)
    disease_ids = set(profile_input.disease_ids)
    if default_ids and not default_ids.issubset(disease_ids):
        return "Default diseases must be included in allowed diseases."
    if UPLOAD_KIND_REMIDIO in upload_kinds and not default_ids:
        return "Select a default disease for Remidio ZIP ingestion."
    if UPLOAD_KIND_REMIDIO not in upload_kinds and default_ids:
        return "Default disease is only used for Remedio ZIP profiles."
    encounter_set_type_ids = set(profile_input.encounter_set_type_ids)
    if UPLOAD_KIND_ENCOUNTER_SET in upload_kinds and not encounter_set_type_ids:
        return "Select at least one EncounterSetType for encounter-set uploads."
    if UPLOAD_KIND_ENCOUNTER_SET not in upload_kinds and encounter_set_type_ids:
        return "EncounterSetTypes are only used when encounter-set uploads are allowed."
    if encounter_set_type_ids:
        valid_encounter_set_types = {
            row[0]: row[1]
            for row in db.execute(
                select(EncounterSetType.id, EncounterSetType.target_scheme_id).where(
                    EncounterSetType.id.in_(encounter_set_type_ids),
                    EncounterSetType.active.is_(True),
                )
            ).all()
        }
        if set(valid_encounter_set_types) != encounter_set_type_ids:
            return "EncounterSetTypes must be active."
        if not set(valid_encounter_set_types.values()).issubset(disease_ids):
            return "EncounterSetType target schemes must be included in allowed target schemes."
    ai_workflows = _valid_ai_workflows(db, profile_input.ai_workflows, disease_ids, set(upload_kinds))
    if ai_workflows is None:
        return "AI workflow disease and upload type must be included in the profile, and AI models must exist."

    profile.name = profile_input.name
    profile.description = profile_input.description
    profile.lab_unit_id = profile_input.lab_unit_id
    profile.project_id = profile_input.project_id
    profile.allow_mydriatic = profile_input.allow_mydriatic
    profile.allow_non_mydriatic = profile_input.allow_non_mydriatic
    profile.default_is_mydriatic = profile_input.default_is_mydriatic

    if profile.id is not None:
        _clear_profile_children(db, profile, clear_assignments=valid_user_ids is not None)

    if valid_user_ids is not None:
        profile.assignments = [UploadProfileAssignment(user_id=user_id, active=True) for user_id in sorted(valid_user_ids)]
    profile.diseases = [
        UploadProfileDisease(disease_id=disease_id, is_default=disease_id in default_ids)
        for disease_id in sorted(disease_ids)
    ]
    profile.cameras = [UploadProfileCamera(camera_id=camera_id) for camera_id in sorted(set(profile_input.camera_ids))]
    profile.areas = [UploadProfileArea(area_id=area_id) for area_id in sorted(set(profile_input.area_ids))]
    profile.upload_kinds = [UploadProfileKind(upload_kind=upload_kind) for upload_kind in upload_kinds]
    profile.encounter_set_types = [
        UploadProfileEncounterSetType(encounter_set_type_id=encounter_set_type_id, active=True)
        for encounter_set_type_id in sorted(encounter_set_type_ids)
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


def _clear_profile_children(db, profile: UploadProfile, *, clear_assignments: bool) -> None:
    """Flush deleted child rows before replacement inserts hit unique constraints."""
    if clear_assignments:
        profile.assignments = []
    profile.diseases = []
    profile.cameras = []
    profile.areas = []
    profile.upload_kinds = []
    profile.encounter_set_types = []
    profile.ai_workflows = []
    db.flush()


def _user_has_lab_unit(db, user_id: int, lab_unit_id: int) -> bool:
    return (
        db.execute(
            select(user_lab_units.c.user_id).where(
                user_lab_units.c.user_id == user_id,
                user_lab_units.c.lab_unit_id == lab_unit_id,
            )
        ).first()
        is not None
    )


def _valid_ai_workflows(
    db,
    workflow_inputs: list[AIWorkflowInput],
    disease_ids: set[int],
    upload_kinds: set[str],
) -> list[AIWorkflowInput] | None:
    deduped: dict[tuple[int, int, str], AIWorkflowInput] = {}
    for workflow in workflow_inputs:
        if workflow.disease_id not in disease_ids or workflow.upload_kind not in upload_kinds:
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
