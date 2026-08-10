"""Runtime eligibility decisions for project and legacy grading tasks."""

from __future__ import annotations

from typing import TypeAlias

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app_cache import cache
from grading_allocation.constants import AllocationCapacity, capacity_for_role_slot
from grading_allocation.dtos import TaskAllocationContext
from grading_allocation.exceptions import AllocationContextError
from grading_allocation.models import ProjectGraderAllocation, ProjectGradingAllocationPolicy
from grading_allocation.resolver import resolve_task_allocation_context
from models import Grade, GradingTask, Role, User, UserDiseaseUnitRole, UserRole
from utils.linkedGradingUtils import get_primary_disease_id


ELIGIBILITY_CACHE_TTL_SECONDS = 300
AllocationKey: TypeAlias = tuple[int, int, str, int | None, int | None, str]
EligibilitySnapshot: TypeAlias = tuple[frozenset[str], frozenset[AllocationKey]]


def is_user_eligible_for_task(
    db: Session,
    *,
    user_id: int,
    task: GradingTask,
    role_slot: str,
) -> bool:
    """Apply project allocation when enabled, otherwise preserve legacy eligibility."""
    capacity = capacity_for_role_slot(role_slot)
    if capacity is None:
        return False
    snapshot = _cached_user_eligibility_snapshot(db, user_id=user_id)
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

    if context.project_id is None or not _project_enforcement_enabled(db, context.project_id):
        return _legacy_eligible(db, user_id=user_id, task=task, capacity=capacity)
    if context.target is None:
        return False

    return _allocation_key(
        context=context,
        capacity=capacity,
    ) in allocation_keys


def invalidate_user_eligibility_cache(user_id: int) -> None:
    """Invalidate stable grading authorization inputs for one user."""
    try:
        cache.delete(_eligibility_cache_key(user_id))
    except Exception:  # Cache is an optimization; authorization falls back to SQL.
        # Domain services and unit tests may run without a Flask app/cache.
        pass


def _eligibility_cache_key(user_id: int) -> str:
    return f"grading-allocation:eligibility:v1:user:{user_id}"


def _cached_user_eligibility_snapshot(
    db: Session,
    *,
    user_id: int,
) -> EligibilitySnapshot | None:
    cache_key = _eligibility_cache_key(user_id)
    try:
        cached = cache.get(cache_key)
    except Exception:  # Cache is an optimization; authorization falls back to SQL.
        cached = None
    if isinstance(cached, dict) and "roles" in cached and "allocations" in cached:
        return (
            frozenset(str(role_name) for role_name in cached["roles"]),
            frozenset(tuple(key) for key in cached["allocations"]),
        )

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
    try:
        cache.set(
            cache_key,
            {
                "roles": sorted(role_names),
                "allocations": [list(key) for key in sorted(allocation_keys, key=repr)],
            },
            timeout=ELIGIBILITY_CACHE_TTL_SECONDS,
        )
    except Exception:  # Cache is an optimization; authorization falls back to SQL.
        pass
    return role_names, allocation_keys


def eligible_enforced_project_task_contexts(
    db: Session,
    *,
    user_id: int,
    task_slots: list[tuple[GradingTask, str]],
    enforced_project_ids: set[int],
) -> dict[tuple[int, str], TaskAllocationContext]:
    """Bulk equivalent of enforced-project task eligibility for dashboards.

    The caller has already selected tasks from projects whose allocation policy
    is enabled. User roles, conflicting grades, and allocations are therefore
    loaded once instead of once per task.
    """
    if not task_slots or not enforced_project_ids:
        return {}
    snapshot = _cached_user_eligibility_snapshot(db, user_id=user_id)
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
            context.project_id not in enforced_project_ids
            or context.target is None
        ):
            continue
        key = _allocation_key(context=context, capacity=capacity)
        if key in allocation_keys:
            eligible[(task.id, role_slot)] = context
    return eligible


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

    effective_disease_id = get_primary_disease_id(db, disease_id)
    legacy_query = select(UserDiseaseUnitRole.lab_unit_id).where(
        UserDiseaseUnitRole.user_id == user_id,
        UserDiseaseUnitRole.disease_id == effective_disease_id,
        UserDiseaseUnitRole.active.is_(True),
    )
    if capacity == AllocationCapacity.RESIDENT:
        legacy_query = legacy_query.where(
            or_(
                UserDiseaseUnitRole.can_grade_resident.is_(True),
                UserDiseaseUnitRole.can_grade_resident2.is_(True),
            )
        )
    else:
        legacy_query = legacy_query.where(UserDiseaseUnitRole.can_arbitrate.is_(True))

    lab_ids = set(db.execute(legacy_query).scalars().all())
    project_lab_ids = db.execute(
        select(ProjectGraderAllocation.lab_unit_id)
        .join(
            ProjectGradingAllocationPolicy,
            ProjectGradingAllocationPolicy.project_id == ProjectGraderAllocation.project_id,
        )
        .where(
            ProjectGraderAllocation.user_id == user_id,
            ProjectGraderAllocation.capacity == capacity.value,
            ProjectGraderAllocation.active.is_(True),
            ProjectGradingAllocationPolicy.enforcement_enabled.is_(True),
        )
    ).scalars().all()
    lab_ids.update(project_lab_ids)
    return sorted(lab_ids) or None


def _project_enforcement_enabled(db: Session, project_id: int) -> bool:
    return bool(
        db.execute(
            select(ProjectGradingAllocationPolicy.enforcement_enabled).where(
                ProjectGradingAllocationPolicy.project_id == project_id
            )
        ).scalar_one_or_none()
    )


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
    if capacity == AllocationCapacity.RESIDENT:
        return bool(role_names & {"resident", "resident2", "ophthalmologist"})
    return bool(role_names & {"arbitrator", "ophthalmologist"})


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
