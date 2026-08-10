"""Resolve immutable grading-allocation meaning from server-owned task data."""

from __future__ import annotations

from sqlalchemy.orm import Session

from grading_allocation.constants import AllocationScope
from grading_allocation.dtos import TargetIdentity, TaskAllocationContext
from grading_allocation.exceptions import AllocationContextError
from models import GradingTask
from upload_profiles.models import UploadProfileEncounterSetTypeGradingPackage


def resolve_task_allocation_context(db: Session, task: GradingTask) -> TaskAllocationContext:
    """Resolve project and semantic target without trusting browser identifiers."""
    project_ids = _source_project_ids(task)
    if len(project_ids) > 1:
        raise AllocationContextError(
            "Task source rows disagree about project ownership.",
            details={"task_id": task.id, "project_ids": list(project_ids)},
        )
    project_id = project_ids[0] if project_ids else None

    if task.encounter_file_id is not None or task.direct_image_upload_id is not None:
        target = TargetIdentity(AllocationScope.DISEASE_IMAGE, disease_id=task.disease_id)
    elif task.encounter_set_image_id is not None or task.patient_encounter_id is not None:
        target = _encounter_set_target(db, task)
    else:
        target = None

    return TaskAllocationContext(
        task_id=task.id,
        project_id=project_id,
        lab_unit_id=task.lab_unit_id,
        target=target,
        source_project_ids=project_ids,
    )


def _source_project_ids(task: GradingTask) -> tuple[int, ...]:
    candidates: set[int] = set()
    if task.encounter_file is not None:
        _add_project(candidates, task.encounter_file.project_id)
        _add_project(candidates, task.encounter_file.patient_encounter.project_id)
    if task.direct_image is not None:
        _add_project(candidates, task.direct_image.project_id)
    if task.patient_encounter is not None:
        _add_project(candidates, task.patient_encounter.project_id)
    if task.encounter_set_image is not None:
        _add_project(candidates, task.encounter_set_image.project_id)
        _add_project(candidates, task.encounter_set_image.patient_encounter.project_id)
    return tuple(sorted(candidates))


def _add_project(candidates: set[int], project_id: int | None) -> None:
    if project_id is not None:
        candidates.add(project_id)


def _encounter_set_target(db: Session, task: GradingTask) -> TargetIdentity | None:
    package = task.encounter_set_package
    if package is None:
        return None
    encounter_set_type_id = package.encounter_set_type_id
    config = None
    if encounter_set_type_id is None and package.upload_profile_est_grading_package_id:
        # Legacy compatibility only. Native packages freeze this identity and
        # remain resolvable after their mutable profile policy is deactivated.
        config = db.get(
            UploadProfileEncounterSetTypeGradingPackage,
            package.upload_profile_est_grading_package_id,
        )
        if config is not None:
            encounter_set_type_id = (
                config.profile_encounter_set_type.encounter_set_type_id
            )
    if encounter_set_type_id is None:
        return None
    if package.grading_mode == "unified":
        return TargetIdentity(
            AllocationScope.ENCOUNTER_SET_UNIFIED,
            encounter_set_type_id=encounter_set_type_id,
        )

    context_disease_id = package.root_scope_disease_id
    if context_disease_id is None:
        context_disease_id = (package.policy_snapshot_json or {}).get("package", {}).get(
            "root_scope_disease_id"
        )
    if context_disease_id is None and config is not None:
        context_disease_id = config.default_image_grading_scheme_id
    if context_disease_id is None and config is not None:
        active_image_schemes = [row for row in config.image_grading_schemes if row.active]
        if len(active_image_schemes) == 1:
            context_disease_id = active_image_schemes[0].disease_id
    if context_disease_id is None:
        return None
    return TargetIdentity(
        AllocationScope.DISEASE_ENCOUNTER,
        disease_id=context_disease_id,
        encounter_set_type_id=encounter_set_type_id,
    )
