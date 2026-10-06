"""Project-owned EncounterSet queues for the grading dashboard."""

from __future__ import annotations

from typing import NamedTuple

from sqlalchemy import and_, case, distinct, exists, func, literal, or_, select, union_all
from sqlalchemy.dialects.postgresql import aggregate_order_by, array_agg
from sqlalchemy.orm import Session, aliased

from grading.workbench.package_workflow import reconcile_active_packages
from grading_allocation.constants import (
    AllocationCapacity,
    AllocationScope,
    capacity_for_role_slot,
)
from grading_allocation.dtos import (
    EncounterSetQueueSlotDTO,
    ProjectEncounterSetQueueDTO,
    ProjectGradingTargetDTO,
    TargetIdentity,
)
from grading_allocation.eligibility import (
    _current_user_eligibility_snapshot,
    _role_names_have_capacity,
)
from grading_allocation.models import ProjectGraderAllocation
from grading_allocation.targets import derive_project_targets
from models import (
    Disease,
    EncounterSetGradingPackage,
    Grade,
    GradingTask,
    PatientEncounters,
    Project,
    TaskTracker,
)
from project_configuration.models import ProjectLabUnit

_SLOT_STATES = {
    "resident": "pending",
    "resident2": "resident_done",
    "arbitrator": "arbitration",
}
_SLOT_ORDER = {slot: index for index, slot in enumerate(_SLOT_STATES)}
# A user's own grade in these slots bars them from the keyed slot.
_CONFLICTING_SLOTS = {
    "resident": ("resident2",),
    "resident2": ("resident",),
    "arbitrator": ("resident", "resident2"),
}


def list_project_encounter_set_queues(
    db: Session,
    *,
    user_id: int,
    reconcile: bool = True,
) -> tuple[ProjectEncounterSetQueueDTO, ...]:
    """Return pending project EncounterSet packages eligible for a user.

    ``reconcile=False`` skips the package-state reconciliation below. Only pass
    it when the caller has already reconciled in this request - the read is
    cacheable, but the reconciliation is a write that advances packages past
    their post-Resident2 waiting period and must not be skipped.

    Eligibility, tracker and conflicting-grade exclusion and the per-slot
    counts are computed in one grouped SQL statement, so no task rows are
    loaded into Python.
    """
    projects = _allocated_projects(db, user_id=user_id)
    if not projects:
        return ()

    if reconcile:
        reconcile_active_packages(db)

    snapshot = _current_user_eligibility_snapshot(db, user_id=user_id)
    if snapshot is None or not _role_names_have_capacity(
        snapshot[0], AllocationCapacity.RESIDENT
    ):
        return ()

    targets_by_project: dict[int, dict[TargetIdentity, ProjectGradingTargetDTO]] = {}
    grouped: dict[tuple[int, TargetIdentity], dict[str, object]] = {}
    for row in db.execute(_eligible_slot_counts(user_id=user_id, project_ids=projects)):
        identity = TargetIdentity(
            AllocationScope(row.scope),
            disease_id=row.target_disease_id,
            encounter_set_type_id=row.target_encounter_set_type_id,
        )
        item = grouped.get((row.project_id, identity))
        if item is None:
            if row.project_id not in targets_by_project:
                targets_by_project[row.project_id] = {
                    target.identity: target
                    for target in derive_project_targets(db, row.project_id)[0]
                }
            target = targets_by_project[row.project_id].get(identity)
            if target is None:
                target = _frozen_package_target(
                    db,
                    db.get(EncounterSetGradingPackage, row.first_package_id),
                    identity,
                )
            item = grouped[(row.project_id, identity)] = {"target": target, "slots": {}}
        item["slots"][row.slot] = EncounterSetQueueSlotDTO(
            slot=row.slot,
            package_count=row.package_count,
            task_count=row.task_count,
            first_package_uuid=row.first_package_uuid,
        )

    return _queue_dtos(projects, grouped)


def _allocated_projects(db: Session, *, user_id: int) -> dict[int, Project]:
    """Active projects where the user holds an active allocation in an active lab."""
    project_rows = db.execute(
        select(Project)
        .join(ProjectGraderAllocation, ProjectGraderAllocation.project_id == Project.id)
        .join(
            ProjectLabUnit,
            and_(
                ProjectLabUnit.project_id == ProjectGraderAllocation.project_id,
                ProjectLabUnit.lab_unit_id == ProjectGraderAllocation.lab_unit_id,
                ProjectLabUnit.active.is_(True),
            ),
        )
        .where(
            Project.active.is_(True),
            ProjectGraderAllocation.user_id == user_id,
            ProjectGraderAllocation.active.is_(True),
        )
        .distinct()
        .order_by(Project.title, Project.id)
    ).scalars().all()
    return {project.id: project for project in project_rows}


def _eligible_slot_counts(*, user_id: int, project_ids):
    """Per (project, target, slot): package/task counts and first package.

    One SELECT per slot, unioned, then grouped. Eligibility is
    ``exact_allocation_predicate`` (the workbench queue's SQL mirror of
    ``grading_allocation.resolver``) plus the tracker and conflicting-grade
    exclusions of ``eligible_project_task_contexts``. "First" package is the
    package of the oldest eligible task, matching the former Python walk.
    """
    per_slot = []
    for slot, state in _SLOT_STATES.items():
        package = aliased(EncounterSetGradingPackage)
        encounter = aliased(PatientEncounters)
        exprs = _allocation_target_exprs(GradingTask, package)
        tracker = select(TaskTracker.id).where(
            TaskTracker.task_id == GradingTask.id,
            TaskTracker.role_slot == slot,
        )
        conflicting_grade = select(Grade.id).where(
            Grade.task_id == GradingTask.id,
            Grade.grader_user_id == user_id,
            Grade.role_slot.in_(_CONFLICTING_SLOTS[slot]),
        )
        per_slot.append(
            select(
                literal(slot).label("slot"),
                encounter.project_id.label("project_id"),
                exprs.scope.label("scope"),
                exprs.disease_id.label("target_disease_id"),
                exprs.encounter_set_type_id.label("target_encounter_set_type_id"),
                package.id.label("package_id"),
                package.uuid.label("package_uuid"),
                GradingTask.id.label("task_id"),
                GradingTask.created_at.label("created_at"),
            )
            .select_from(GradingTask)
            .join(package, package.id == GradingTask.encounter_set_package_id)
            .join(encounter, encounter.id == package.patient_encounter_id)
            .where(
                encounter.project_id.in_(list(project_ids)),
                GradingTask.state == state,
                exact_allocation_predicate(
                    GradingTask,
                    package,
                    user_id=user_id,
                    capacity=capacity_for_role_slot(slot).value,
                ),
                ~exists(tracker),
                ~exists(conflicting_grade),
            )
        )
    rows = union_all(*per_slot).subquery()
    oldest_first = (rows.c.created_at, rows.c.task_id)
    return select(
        rows.c.project_id,
        rows.c.scope,
        rows.c.target_disease_id,
        rows.c.target_encounter_set_type_id,
        rows.c.slot,
        func.count(distinct(rows.c.package_id)).label("package_count"),
        func.count(distinct(rows.c.task_id)).label("task_count"),
        array_agg(aggregate_order_by(rows.c.package_uuid, *oldest_first))[1].label(
            "first_package_uuid"
        ),
        array_agg(aggregate_order_by(rows.c.package_id, *oldest_first))[1].label(
            "first_package_id"
        ),
    ).group_by(
        rows.c.project_id,
        rows.c.scope,
        rows.c.target_disease_id,
        rows.c.target_encounter_set_type_id,
        rows.c.slot,
    )


def _queue_dtos(
    projects: dict[int, Project],
    grouped: dict[tuple[int, TargetIdentity], dict[str, object]],
) -> tuple[ProjectEncounterSetQueueDTO, ...]:
    queues: list[ProjectEncounterSetQueueDTO] = []
    for (project_id, target_identity), item in grouped.items():
        project = projects[project_id]
        target = item["target"]
        slots = tuple(
            item["slots"][slot]
            for slot in sorted(item["slots"], key=_SLOT_ORDER.get)
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


def exclude_project_encounter_set_tasks(query, task_entity=GradingTask):
    """Exclude project-owned EncounterSet tasks from classical queues."""
    project_task = (
        select(EncounterSetGradingPackage.id)
        .join(
            PatientEncounters,
            PatientEncounters.id == EncounterSetGradingPackage.patient_encounter_id,
        )
        .where(
            EncounterSetGradingPackage.id == task_entity.encounter_set_package_id,
            PatientEncounters.project_id.is_not(None),
        )
        .correlate(task_entity)
    )
    return query.filter(~exists(project_task))

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
    project_lab_membership = (
        select(ProjectLabUnit.id)
        .where(
            ProjectLabUnit.project_id == project_id,
            ProjectLabUnit.lab_unit_id == inner.lab_unit_id,
            ProjectLabUnit.active.is_(True),
        )
        .correlate(inner)
    )
    allocated = select(ProjectGraderAllocation.id).where(
        *allocation_conditions,
        exists(project_lab_membership),
    )

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


class _TargetExprs(NamedTuple):
    scope: object
    disease_id: object
    encounter_set_type_id: object
    resolvable: object


def _allocation_target_exprs(task_entity, package) -> _TargetExprs:
    """SQL form of ``resolver.resolve_task_allocation_context``'s target."""
    is_image_task = or_(
        task_entity.encounter_file_id.isnot(None),
        task_entity.direct_image_upload_id.isnot(None),
    )
    is_unified = package.grading_mode == "unified"
    return _TargetExprs(
        scope=case(
            (is_image_task, literal(AllocationScope.DISEASE_IMAGE.value)),
            (is_unified, literal(AllocationScope.ENCOUNTER_SET_UNIFIED.value)),
            else_=literal(AllocationScope.DISEASE_ENCOUNTER.value),
        ),
        disease_id=case(
            (is_image_task, task_entity.disease_id),
            (is_unified, literal(None)),
            else_=package.root_scope_disease_id,
        ),
        encounter_set_type_id=case(
            (is_image_task, literal(None)),
            else_=package.encounter_set_type_id,
        ),
        resolvable=or_(
            is_image_task,
            and_(is_unified, package.encounter_set_type_id.isnot(None)),
            and_(
                ~is_unified,
                package.encounter_set_type_id.isnot(None),
                package.root_scope_disease_id.isnot(None),
            ),
        ),
    )


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
    exprs = _allocation_target_exprs(task_entity, package)
    scope_expr = exprs.scope
    target_disease_expr = exprs.disease_id
    target_resolvable = exprs.resolvable

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
    project_lab_match = select(ProjectLabUnit.id).where(
        ProjectLabUnit.project_id == task_entity.project_id,
        ProjectLabUnit.lab_unit_id == task_entity.lab_unit_id,
        ProjectLabUnit.active.is_(True),
    )
    return and_(
        target_resolvable,
        exists(project_lab_match),
        exists(allocation_match),
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
            exact_allocation_predicate(
                task_entity, package, user_id=user_id, capacity=capacity
            ),
        )
    )
