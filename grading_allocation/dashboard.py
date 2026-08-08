"""Project-owned EncounterSet queues for the grading dashboard."""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import exists, select
from sqlalchemy.orm import Session, selectinload

from grading_allocation.dtos import (
    EncounterSetQueueSlotDTO,
    ProjectEncounterSetQueueDTO,
)
from grading_allocation.eligibility import is_user_eligible_for_task
from grading_allocation.models import ProjectGradingAllocationPolicy
from grading_allocation.resolver import resolve_task_allocation_context
from grading_allocation.targets import derive_project_targets
from models import (
    EncounterSetGradingPackage,
    EncounterSetImage,
    GradingTask,
    PatientEncounters,
    Project,
    TaskTracker,
)


_SLOT_STATES = {
    "resident": "pending",
    "resident2": "resident_done",
    "arbitrator": "arbitration",
}
_SLOT_ORDER = {slot: index for index, slot in enumerate(_SLOT_STATES)}


def list_project_encounter_set_queues(
    db: Session,
    *,
    user_id: int,
) -> tuple[ProjectEncounterSetQueueDTO, ...]:
    """Return pending enforced-project EncounterSet packages eligible for a user."""
    project_rows = db.execute(
        select(Project)
        .join(
            ProjectGradingAllocationPolicy,
            ProjectGradingAllocationPolicy.project_id == Project.id,
        )
        .where(ProjectGradingAllocationPolicy.enforcement_enabled.is_(True))
        .order_by(Project.title, Project.id)
    ).scalars().all()
    projects = {project.id: project for project in project_rows}
    if not projects:
        return ()

    tasks = (
        db.execute(
            select(GradingTask)
            .join(
                EncounterSetGradingPackage,
                EncounterSetGradingPackage.id == GradingTask.encounter_set_package_id,
            )
            .join(
                PatientEncounters,
                PatientEncounters.id == EncounterSetGradingPackage.patient_encounter_id,
            )
            .where(PatientEncounters.project_id.in_(projects))
            .where(GradingTask.state.in_(tuple(_SLOT_STATES.values())))
            .options(
                selectinload(GradingTask.patient_encounter),
                selectinload(GradingTask.encounter_set_image).selectinload(
                    EncounterSetImage.patient_encounter
                ),
                selectinload(GradingTask.encounter_set_package).selectinload(
                    EncounterSetGradingPackage.patient_encounter
                ),
                selectinload(GradingTask.encounter_set_package).selectinload(
                    EncounterSetGradingPackage.tasks
                ),
                selectinload(GradingTask.grades),
            )
            .order_by(GradingTask.created_at, GradingTask.id)
        )
        .scalars()
        .all()
    )
    if not tasks:
        return ()

    tracker_keys = set(
        db.execute(
            select(TaskTracker.task_id, TaskTracker.role_slot).where(
                TaskTracker.task_id.in_([task.id for task in tasks])
            )
        ).all()
    )
    targets_by_project = {
        project_id: {
            target.identity: target
            for target in derive_project_targets(db, project_id)[0]
        }
        for project_id in projects
    }
    grouped: dict[tuple[int, object], dict[str, object]] = {}

    for task in tasks:
        context = resolve_task_allocation_context(db, task)
        if context.project_id not in projects or context.target is None:
            continue
        target = targets_by_project[context.project_id].get(context.target)
        if target is None:
            continue
        slot = next(
            (
                candidate_slot
                for candidate_slot, state in _SLOT_STATES.items()
                if state == task.state
            ),
            None,
        )
        if slot is None or (task.id, slot) in tracker_keys:
            continue
        if not is_user_eligible_for_task(
            db,
            user_id=user_id,
            task=task,
            role_slot=slot,
        ):
            continue

        package = task.encounter_set_package
        if package is None:
            continue
        item = grouped.setdefault(
            (context.project_id, context.target),
            {
                "target": target,
                "packages": defaultdict(dict),
                "tasks": defaultdict(set),
            },
        )
        item["packages"][slot].setdefault(package.uuid, task.id)
        item["tasks"][slot].add(task.id)

    queues: list[ProjectEncounterSetQueueDTO] = []
    for (project_id, target_identity), item in grouped.items():
        project = projects[project_id]
        target = item["target"]
        slots = tuple(
            EncounterSetQueueSlotDTO(
                slot=slot,
                package_count=len(item["packages"][slot]),
                task_count=len(item["tasks"][slot]),
                first_package_uuid=next(iter(item["packages"][slot])),
            )
            for slot in sorted(item["packages"], key=_SLOT_ORDER.get)
            if item["packages"][slot]
        )
        if slots:
            queues.append(
                ProjectEncounterSetQueueDTO(
                    project_id=project.id,
                    project_title=project.title,
                    project_code=project.code,
                    target_key=target_identity.key,
                    target_label=(
                        f"{target.disease_name} / EncounterSet"
                        if target.disease_name
                        else "Unified EncounterSet"
                    ),
                    encounter_set_type_name=target.encounter_set_type_name,
                    slots=slots,
                )
            )
    return tuple(
        sorted(
            queues,
            key=lambda queue: (
                queue.project_title.lower(),
                queue.target_label.lower(),
                queue.target_key,
            ),
        )
    )


def exclude_enforced_project_encounter_set_tasks(query, task_entity=GradingTask):
    """Exclude tasks owned by EncounterSet packages in enforced projects."""
    enforced_task = (
        select(EncounterSetGradingPackage.id)
        .join(
            PatientEncounters,
            PatientEncounters.id == EncounterSetGradingPackage.patient_encounter_id,
        )
        .join(
            ProjectGradingAllocationPolicy,
            ProjectGradingAllocationPolicy.project_id == PatientEncounters.project_id,
        )
        .where(
            EncounterSetGradingPackage.id == task_entity.encounter_set_package_id,
            ProjectGradingAllocationPolicy.enforcement_enabled.is_(True),
        )
        .correlate(task_entity)
    )
    return query.filter(~exists(enforced_task))
