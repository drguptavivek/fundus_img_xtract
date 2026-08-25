"""Project-owned EncounterSet queues for the grading dashboard."""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import and_, case, exists, literal, select, func, or_
from sqlalchemy.orm import Session, selectinload, aliased

from grading.workbench.package_workflow import reconcile_active_packages
from grading_allocation.constants import AllocationScope
from grading_allocation.dtos import (
    EncounterSetQueueSlotDTO,
    ProjectGradingTargetDTO,
    ProjectEncounterSetQueueDTO,
    TargetIdentity,
)
from grading_allocation.eligibility import eligible_enforced_project_task_contexts
from grading_allocation.models import ProjectGraderAllocation, ProjectGradingAllocationPolicy
from grading_allocation.targets import derive_project_targets
from models import (
    EncounterSetGradingPackage,
    EncounterSetImage,
    Disease,
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
    reconcile: bool = True,
) -> tuple[ProjectEncounterSetQueueDTO, ...]:
    """Return pending enforced-project EncounterSet packages eligible for a user.

    ``reconcile=False`` skips the package-state reconciliation below. Only pass
    it when the caller has already reconciled in this request - the read is
    cacheable, but the reconciliation is a write that advances packages past
    their post-Resident2 waiting period and must not be skipped.
    """
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

    if reconcile:
        reconcile_active_packages(db)

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
    task_slots = []
    for task in tasks:
        slot = next(
            (
                candidate_slot
                for candidate_slot, state in _SLOT_STATES.items()
                if state == task.state
            ),
            None,
        )
        if slot is not None and (task.id, slot) not in tracker_keys:
            task_slots.append((task, slot))
    eligible_contexts = eligible_enforced_project_task_contexts(
        db,
        user_id=user_id,
        task_slots=task_slots,
        enforced_project_ids=set(projects),
    )
    grouped: dict[tuple[int, object], dict[str, object]] = {}

    for task, slot in task_slots:
        context = eligible_contexts.get((task.id, slot))
        if context is None:
            continue
        if context.project_id not in projects or context.target is None:
            continue
        target = targets_by_project[context.project_id].get(context.target)
        if target is None:
            target = _frozen_package_target(db, task.encounter_set_package, context.target)
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


def _frozen_package_target(
    db: Session,
    package: EncounterSetGradingPackage,
    identity: TargetIdentity,
) -> ProjectGradingTargetDTO:
    """Build queue display data without consulting mutable profile policy."""
    snapshot = package.policy_snapshot_json or {}
    definitions = snapshot.get("grading_definitions") or {}
    disease_name = None
    if identity.disease_id is not None:
        disease_name = (definitions.get(str(identity.disease_id)) or {}).get("name")
        if disease_name is None:
            disease = db.get(Disease, identity.disease_id)
            disease_name = disease.name if disease else f"Disease {identity.disease_id}"
    encounter_set_type_name = (snapshot.get("encounter_set_type") or {}).get("name")
    if encounter_set_type_name is None:
        encounter_set_type_name = f"EncounterSet type {identity.encounter_set_type_id}"
    return ProjectGradingTargetDTO(
        identity=identity,
        label=(
            f"{disease_name} / EncounterSet"
            if disease_name
            else "Unified EncounterSet"
        ),
        disease_name=disease_name,
        encounter_set_type_name=encounter_set_type_name,
        grading_scheme_ids={task.disease_id for task in package.tasks},
        diseases={
            int(disease_id): definition.get("name") or f"Disease {disease_id}"
            for disease_id, definition in definitions.items()
            if str(disease_id).isdigit()
        },
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

def exclude_unallocated_project_tasks(
    query,
    *,
    user_id: int,
    capacity: str,
    disease_id: int | None = None,
    task_entity=GradingTask,
):
    """Drop project-owned tasks the user holds no allocation for.

    Tasks belonging to no project are untouched: those follow the classical
    grading-slot rule. A task owned by a project survives only if the user
    holds an active allocation in that project, for that lab unit and
    capacity, and either the allocation names no disease or names this one.

    Precision note: an allocation scoped to a particular EncounterSet type is
    matched here only on project, lab, capacity and disease, so a count can
    still include a task of a different EncounterSet type. That errs towards
    showing work rather than hiding it; the exact check runs per task in
    ``grading_allocation.eligibility.is_user_eligible_for_task`` before the
    task can actually be opened.
    """
    inner = aliased(task_entity)

    # Owning project is denormalised onto the task by
    # trg_grading_tasks_apply_project_id, so this no longer outer-joins the six
    # source tables to coalesce it at read time.
    project_id = inner.project_id

    allocation_conditions = [
        ProjectGraderAllocation.user_id == user_id,
        ProjectGraderAllocation.active.is_(True),
        ProjectGraderAllocation.capacity == capacity,
        ProjectGraderAllocation.project_id == project_id,
        ProjectGraderAllocation.lab_unit_id == inner.lab_unit_id,
    ]
    if disease_id is not None:
        allocation_conditions.append(
            or_(
                ProjectGraderAllocation.disease_id.is_(None),
                ProjectGraderAllocation.disease_id == disease_id,
            )
        )
    allocated = select(ProjectGraderAllocation.id).where(*allocation_conditions)

    # "This task belongs to a project and the user has no allocation for it."
    unallocated = (
        select(inner.id)
        .select_from(inner)
        .where(
            inner.id == task_entity.id,
            project_id.isnot(None),
            ~exists(allocated),
        )
        .correlate(task_entity)
    )
    return query.filter(~exists(unallocated))


def exact_allocation_predicate(task_entity, package, *, user_id: int, capacity: str):
    """SQL form of the enforced-project half of ``is_user_eligible_for_task``.

    ``package`` must be an ``EncounterSetGradingPackage`` alias already outer
    joined to ``task_entity.encounter_set_package_id``.

    Mirrors ``grading_allocation.resolver`` exactly, including its refusal to
    grant access when the target identity cannot be resolved: Python returns a
    ``None`` target for an EncounterSet task with no resolvable type or root
    disease, and such a task is never eligible. ``target_resolvable`` below is
    that same rule, so the two cannot diverge into granting access.
    """
    is_image_task = or_(
        task_entity.encounter_file_id.isnot(None),
        task_entity.direct_image_upload_id.isnot(None),
    )
    is_unified = package.grading_mode == "unified"

    scope_expr = case(
        (is_image_task, literal(AllocationScope.DISEASE_IMAGE.value)),
        (is_unified, literal(AllocationScope.ENCOUNTER_SET_UNIFIED.value)),
        else_=literal(AllocationScope.DISEASE_ENCOUNTER.value),
    )
    target_disease_expr = case(
        (is_image_task, task_entity.disease_id),
        (is_unified, literal(None)),
        else_=package.root_scope_disease_id,
    )
    target_resolvable = or_(
        is_image_task,
        and_(is_unified, package.encounter_set_type_id.isnot(None)),
        and_(
            ~is_unified,
            package.encounter_set_type_id.isnot(None),
            package.root_scope_disease_id.isnot(None),
        ),
    )

    allocation_match = select(ProjectGraderAllocation.id).where(
        ProjectGraderAllocation.user_id == user_id,
        ProjectGraderAllocation.active.is_(True),
        ProjectGraderAllocation.capacity == capacity,
        ProjectGraderAllocation.project_id == task_entity.project_id,
        ProjectGraderAllocation.lab_unit_id == task_entity.lab_unit_id,
        ProjectGraderAllocation.scope == scope_expr,
        ProjectGraderAllocation.disease_id.is_not_distinct_from(target_disease_expr),
        ProjectGraderAllocation.encounter_set_type_id.is_not_distinct_from(
            package.encounter_set_type_id
        ),
    )
    return and_(target_resolvable, exists(allocation_match))


def project_enforces_allocation(task_entity):
    """Whether this task's owning project has allocation enforcement enabled."""
    return exists(
        select(ProjectGradingAllocationPolicy.project_id).where(
            ProjectGradingAllocationPolicy.project_id == task_entity.project_id,
            ProjectGradingAllocationPolicy.enforcement_enabled.is_(True),
        )
    )


def filter_to_exact_allocation(
    query,
    *,
    user_id: int,
    capacity: str,
    task_entity=GradingTask,
):
    """Keep only tasks this user may actually open, decided entirely in SQL.

    This is the counting-time equivalent of
    ``grading_allocation.eligibility.is_user_eligible_for_task``. That function
    resolves one task at a time from loaded ORM objects, which forced callers
    that wanted a *count* to materialise the whole queue first. The same rule is
    expressed here as a predicate so a count stays a count.
    """
    package = aliased(EncounterSetGradingPackage)
    query = query.outerjoin(
        package, package.id == task_entity.encounter_set_package_id
    )
    return query.filter(
        or_(
            task_entity.project_id.is_(None),
            ~project_enforces_allocation(task_entity),
            exact_allocation_predicate(
                task_entity, package, user_id=user_id, capacity=capacity
            ),
        )
    )
