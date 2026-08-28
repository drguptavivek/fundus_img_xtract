"""Runtime eligibility decisions for project and legacy grading tasks."""

from __future__ import annotations

from typing import TypeAlias

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from grading_allocation.constants import AllocationCapacity, capacity_for_role_slot
from grading_allocation.dtos import TaskAllocationContext
from grading_allocation.exceptions import AllocationContextError
from grading_allocation.models import ProjectGraderAllocation
from grading_allocation.resolver import resolve_task_allocation_context
from models import Grade, GradingTask, Role, User, UserDiseaseUnitRole, UserRole
from utils.linkedGradingUtils import get_primary_disease_id


AllocationKey: TypeAlias = tuple[int, int, str, int | None, int | None, str]
EligibilitySnapshot: TypeAlias = tuple[frozenset[str], frozenset[AllocationKey]]


def is_user_eligible_for_task(
    db: Session,
    *,
    user_id: int,
    task: GradingTask,
    role_slot: str,
) -> bool:
    """Apply classical eligibility or mandatory exact project allocation."""
    capacity = capacity_for_role_slot(role_slot)
    if capacity is None:
        return False
    snapshot = _current_user_eligibility_snapshot(db, user_id=user_id)
    if snapshot is None:
        return False
    role_names, allocation_keys = snapshot
    if not _role_names_have_capacity(role_names, capacity):
        return False
    if _has_conflicting_grade(db, user_id=user_id, task_id=task.id, role_slot=role_slot):
        return False
    try:
        context = resolve_task_allocation_context(db, task)
    except AllocationContextError:
        return False

    if context.project_id is None:
        return _legacy_eligible(db, user_id=user_id, task=task, capacity=capacity)
    if context.target is None:
        return False

    return _allocation_key(
        context=context,
        capacity=capacity,
    ) in allocation_keys


def _current_user_eligibility_snapshot(
    db: Session,
    *,
    user_id: int,
) -> EligibilitySnapshot | None:
    role_names = frozenset(
        db.execute(
            select(Role.name)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user_id)
        ).scalars()
    )
    allocation_keys = frozenset(
        (
            allocation.project_id,
            allocation.lab_unit_id,
            allocation.scope,
            allocation.disease_id,
            allocation.encounter_set_type_id,
            allocation.capacity,
        )
        for allocation in db.execute(
            select(ProjectGraderAllocation).where(
                ProjectGraderAllocation.user_id == user_id,
                ProjectGraderAllocation.active.is_(True),
            )
        ).scalars()
    )
    return role_names, allocation_keys


def eligible_project_task_contexts(
    db: Session,
    *,
    user_id: int,
    task_slots: list[tuple[GradingTask, str]],
    project_ids: set[int],
) -> dict[tuple[int, str], TaskAllocationContext]:
    """Bulk equivalent of project task eligibility for dashboards.

    Every project-owned task requires an exact allocation. User roles,
    conflicting grades, and allocations are loaded once instead of once per
    task. ``project_ids`` is retained as the caller's selected project
    set; it no longer represents an optional policy switch.
    """
    if not task_slots or not project_ids:
        return {}
    snapshot = _current_user_eligibility_snapshot(db, user_id=user_id)
    if snapshot is None:
        return {}
    role_names, allocation_keys = snapshot

    task_ids = sorted({task.id for task, _slot in task_slots})
    user_grade_slots = {}
    for task_id, role_slot in db.execute(
        select(Grade.task_id, Grade.role_slot).where(
            Grade.task_id.in_(task_ids),
            Grade.grader_user_id == user_id,
        )
    ).all():
        user_grade_slots.setdefault(task_id, set()).add(role_slot)

    eligible: dict[tuple[int, str], TaskAllocationContext] = {}
    for task, role_slot in task_slots:
        capacity = capacity_for_role_slot(role_slot)
        if capacity is None or not _role_names_have_capacity(role_names, capacity):
            continue
        conflicting_slots = {
            "resident": {"resident2"},
            "resident2": {"resident"},
            "arbitrator": {"resident", "resident2"},
        }.get(role_slot, set())
        if user_grade_slots.get(task.id, set()).intersection(conflicting_slots):
            continue
        try:
            context = resolve_task_allocation_context(db, task)
        except AllocationContextError:
            continue
        if (
            context.project_id not in project_ids
            or context.target is None
        ):
            continue
        key = _allocation_key(context=context, capacity=capacity)
        if key in allocation_keys:
            eligible[(task.id, role_slot)] = context
    return eligible


def legacy_eligible_lab_unit_ids(
    db: Session,
    *,
    user_id: int,
    disease_id: int,
    capacity: AllocationCapacity,
    lab_unit_ids=None,
) -> list[int]:
    """Labs where the user holds legacy disease/lab eligibility for a capacity.

    This is the set form of ``_legacy_eligible``. Queue selection needs it
    because ``eligible_lab_unit_ids`` returns legacy labs *unioned* with
    enforced-project allocation labs, so membership there does not imply legacy
    eligibility and the two branches must be separated again downstream.
    """
    effective_disease_id = get_primary_disease_id(db, disease_id)
    query = select(UserDiseaseUnitRole.lab_unit_id).where(
        UserDiseaseUnitRole.user_id == user_id,
        UserDiseaseUnitRole.disease_id == effective_disease_id,
        UserDiseaseUnitRole.active.is_(True),
    )
    if capacity == AllocationCapacity.RESIDENT:
        query = query.where(
            or_(
                UserDiseaseUnitRole.can_grade_resident.is_(True),
                UserDiseaseUnitRole.can_grade_resident2.is_(True),
            )
        )
    else:
        query = query.where(UserDiseaseUnitRole.can_arbitrate.is_(True))
    if lab_unit_ids:
        query = query.where(UserDiseaseUnitRole.lab_unit_id.in_(list(lab_unit_ids)))
    return sorted(set(db.execute(query).scalars().all()))


def eligible_lab_unit_ids(
    db: Session,
    *,
    user_id: int,
    disease_id: int,
    role_slot: str,
) -> list[int] | None:
    """Return candidate labs; exact project/target eligibility is checked per task."""
    capacity = capacity_for_role_slot(role_slot)
    if capacity is None:
        return None
    user = (
        db.execute(
            select(User).options(selectinload(User.roles)).where(User.id == user_id)
        )
        .scalars()
        .one_or_none()
    )
    if user is None or not _user_has_capacity_role(user, capacity):
        return None

    lab_ids = set(
        legacy_eligible_lab_unit_ids(
            db, user_id=user_id, disease_id=disease_id, capacity=capacity
        )
    )
    project_lab_ids = db.execute(
        select(ProjectGraderAllocation.lab_unit_id).where(
            ProjectGraderAllocation.user_id == user_id,
            ProjectGraderAllocation.capacity == capacity.value,
            ProjectGraderAllocation.active.is_(True),
        )
    ).scalars().all()
    lab_ids.update(project_lab_ids)
    return sorted(lab_ids) or None


def _has_conflicting_grade(
    db: Session,
    *,
    user_id: int,
    task_id: int,
    role_slot: str,
) -> bool:
    conflicting_slots = {
        "resident": ("resident2",),
        "resident2": ("resident",),
        "arbitrator": ("resident", "resident2"),
    }.get(role_slot, ())
    if not conflicting_slots:
        return False
    return (
        db.execute(
            select(Grade.id).where(
                Grade.task_id == task_id,
                Grade.grader_user_id == user_id,
                Grade.role_slot.in_(conflicting_slots),
            )
        ).scalars().first()
        is not None
    )


def _legacy_eligible(
    db: Session,
    *,
    user_id: int,
    task: GradingTask,
    capacity: AllocationCapacity,
) -> bool:
    effective_disease_id = get_primary_disease_id(db, task.disease_id)
    query = select(UserDiseaseUnitRole.id).where(
        UserDiseaseUnitRole.user_id == user_id,
        UserDiseaseUnitRole.disease_id == effective_disease_id,
        UserDiseaseUnitRole.lab_unit_id == task.lab_unit_id,
        UserDiseaseUnitRole.active.is_(True),
    )
    if capacity == AllocationCapacity.RESIDENT:
        query = query.where(
            or_(
                UserDiseaseUnitRole.can_grade_resident.is_(True),
                UserDiseaseUnitRole.can_grade_resident2.is_(True),
            )
        )
    else:
        query = query.where(UserDiseaseUnitRole.can_arbitrate.is_(True))
    return db.execute(query).scalar_one_or_none() is not None


def _user_has_capacity_role(user: User, capacity: AllocationCapacity) -> bool:
    return _role_names_have_capacity(
        frozenset(role.name for role in user.roles),
        capacity,
    )


def _role_names_have_capacity(
    role_names: frozenset[str],
    capacity: AllocationCapacity,
) -> bool:
    """Whether the user's global roles qualify them to fill a grading slot.

    This checks the user-level qualification only; the slot itself comes from
    UserDiseaseUnitRole or ProjectGraderAllocation and is checked separately,
    so both halves must hold.

    ``resident2`` and ``arbitrator`` are slot names, not roles - no such rows
    exist in the roles table - so testing for them here never matched. The
    qualification to grade, whichever slot is being filled, is the
    ``ophthalmologist`` role.
    """
    return "ophthalmologist" in role_names


def _allocation_key(
    *,
    context: TaskAllocationContext,
    capacity: AllocationCapacity,
) -> AllocationKey:
    target = context.target
    assert context.project_id is not None and target is not None
    return (
        context.project_id,
        context.lab_unit_id,
        target.scope.value,
        target.disease_id,
        target.encounter_set_type_id,
        capacity.value,
    )
