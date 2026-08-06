"""Runtime eligibility decisions for project and legacy grading tasks."""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from grading_allocation.constants import AllocationCapacity, capacity_for_role_slot
from grading_allocation.exceptions import AllocationContextError
from grading_allocation.models import ProjectGraderAllocation, ProjectGradingAllocationPolicy
from grading_allocation.resolver import resolve_task_allocation_context
from models import Grade, GradingTask, User, UserDiseaseUnitRole
from utils.linkedGradingUtils import get_primary_disease_id


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
    user = (
        db.execute(
            select(User).options(selectinload(User.roles)).where(User.id == user_id)
        )
        .scalars()
        .one_or_none()
    )
    if user is None or not _user_has_capacity_role(user, capacity):
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

    target = context.target
    return (
        db.execute(
            select(ProjectGraderAllocation.id).where(
                ProjectGraderAllocation.project_id == context.project_id,
                ProjectGraderAllocation.user_id == user_id,
                ProjectGraderAllocation.lab_unit_id == context.lab_unit_id,
                ProjectGraderAllocation.scope == target.scope.value,
                ProjectGraderAllocation.disease_id.is_(target.disease_id)
                if target.disease_id is None
                else ProjectGraderAllocation.disease_id == target.disease_id,
                ProjectGraderAllocation.encounter_set_type_id.is_(target.encounter_set_type_id)
                if target.encounter_set_type_id is None
                else ProjectGraderAllocation.encounter_set_type_id == target.encounter_set_type_id,
                ProjectGraderAllocation.capacity == capacity.value,
                ProjectGraderAllocation.active.is_(True),
            )
        ).scalar_one_or_none()
        is not None
    )


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
    if capacity == AllocationCapacity.RESIDENT:
        return user.has_role("resident", "resident2", "ophthalmologist")
    return user.has_role("arbitrator", "ophthalmologist")
