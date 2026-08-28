"""Authoritative next-task selection for the grading workbench.

The durable session-target lease is the concurrency boundary.  This module
does not create or consult the legacy ``TaskTracker`` rows.
"""

from __future__ import annotations

import random
from datetime import timedelta

from sqlalchemy import and_, exists, false as sa_false, func, or_
from sqlalchemy.orm import aliased

from grading_allocation.constants import capacity_for_role_slot
from grading_allocation.dashboard import (
    exact_allocation_predicate,
)
from grading_allocation.eligibility import (
    eligible_lab_unit_ids,
    is_user_eligible_for_task,
    legacy_eligible_lab_unit_ids,
)
from models import (
    EncounterSetGradingPackage,
    Grade,
    GradingTask,
    LinkedDiseaseGrading,
)
from .models import GradingWorkbenchSession, GradingWorkbenchSessionTarget
from .package_workflow import reconcile_active_packages
from .linked_tasks import get_linked_disease_ids
from auth.utils import utcnow


def _build_candidate_query(
    db, *, user_id: int, disease_id: int, role_slot: str, lab_unit_id: int | None
):
    """The queue's structural filters, before allocation eligibility.

    Extracted so selection and its verification exercise exactly the same
    predicates. Returns ``(query, labs)`` or ``None`` when the user has no
    eligible lab for this disease and slot.
    """
    labs = eligible_lab_unit_ids(
        db, user_id=user_id, disease_id=disease_id, role_slot=role_slot
    )
    if not labs or (lab_unit_id is not None and lab_unit_id not in labs):
        return None
    if lab_unit_id is not None:
        labs = [lab_unit_id]
    if role_slot == "arbitrator":
        reconcile_active_packages(db)

    states = {
        "resident": ("pending", "resident2_done"),
        "resident2": ("resident_done",),
        "arbitrator": ("arbitration",),
    }[role_slot]
    active_lease = (
        db.query(GradingWorkbenchSessionTarget.id)
        .join(GradingWorkbenchSession)
        .filter(
            GradingWorkbenchSessionTarget.task_id == GradingTask.id,
            GradingWorkbenchSessionTarget.role_slot == role_slot,
            GradingWorkbenchSessionTarget.released_at.is_(None),
            GradingWorkbenchSession.status == "active",
        )
    )
    query = db.query(GradingTask).filter(
        GradingTask.lab_unit_id.in_(labs),
        GradingTask.disease_id == disease_id,
        GradingTask.state.in_(states),
        ~active_lease.exists(),
    )
    if role_slot in {"resident", "resident2"}:
        opposite = "resident2" if role_slot == "resident" else "resident"
        opposite_grade = db.query(Grade.id).filter(
            Grade.task_id == GradingTask.id,
            Grade.grader_user_id == user_id,
            Grade.role_slot == opposite,
        )
        query = query.filter(~opposite_grade.exists())
        query = _exclude_linked_state_mismatches(db, query, disease_id)
    if role_slot == "resident":
        resident2_grade = db.query(Grade.id).filter(
            Grade.task_id == GradingTask.id, Grade.role_slot == "resident2"
        )
        resident_grade = db.query(Grade.id).filter(
            Grade.task_id == GradingTask.id, Grade.role_slot == "resident"
        )
        query = query.filter(
            or_(
                GradingTask.state == "pending",
                and_(
                    GradingTask.state == "resident2_done",
                    resident2_grade.exists(),
                    ~resident_grade.exists(),
                ),
            )
        )
    if role_slot == "arbitrator":
        recent_user_grade = db.query(Grade.id).filter(
            Grade.task_id == GradingTask.id,
            Grade.grader_user_id == user_id,
            Grade.created_at >= utcnow() - timedelta(weeks=4),
        )
        query = query.filter(~recent_user_grade.exists())

    return query, labs


def select_next_task(db, *, user_id: int, disease_id: int, role_slot: str, lab_unit_id: int | None):
    built = _build_candidate_query(
        db,
        user_id=user_id,
        disease_id=disease_id,
        role_slot=role_slot,
        lab_unit_id=lab_unit_id,
    )
    if built is None:
        return None
    query, labs = built
    # Eligibility is decided in SQL rather than by loading the queue and
    # filtering it in Python. The previous shape sorted every eligible row by
    # random(), hydrated it through five joinedloads and walked it; an empty
    # queue paid that in full before it could report "no work". Selection is
    # still random, and the lease below is still what actually claims a task.
    query = _apply_sql_eligibility(
        db,
        query,
        user_id=user_id,
        role_slot=role_slot,
        disease_id=disease_id,
        labs=labs,
    )

    candidate_ids = [row[0] for row in query.with_entities(GradingTask.id).distinct()]
    if not candidate_ids:
        return None
    # Shuffled here rather than by ORDER BY random(), which cannot use an index
    # and forces the database to sort the whole candidate set before returning
    # its first row.
    random.shuffle(candidate_ids)

    for task_id in candidate_ids:
        locked = _lock_available_candidate(db, task_id, role_slot)
        if locked is not None:
            return locked
    return None


# Slots whose grade by the same user disqualifies them from filling this slot.
_CONFLICTING_SLOTS = {
    "resident": ("resident2",),
    "resident2": ("resident",),
    "arbitrator": ("resident", "resident2"),
}


def _apply_sql_eligibility(
    db, query, *, user_id: int, role_slot: str, disease_id: int, labs
):
    """Narrow a queue to tasks this user may actually open.

    Mirrors ``grading_allocation.eligibility.is_user_eligible_for_task``:

    * a conflicting grade by this user disqualifies the task, whatever the
      owning project;
    * every project-owned task needs an exact allocation match;
    * only classical tasks fall back to disease/lab eligibility.

    ``eligible_lab_unit_ids`` returns the union of legacy labs and project
    project-allocation labs, so a lab in ``labs`` does not by itself imply
    legacy eligibility. The legacy branch is therefore re-narrowed to the
    legacy subset here.
    """
    capacity = capacity_for_role_slot(role_slot)
    if capacity is None:
        return query.filter(sa_false())

    conflicting = _CONFLICTING_SLOTS.get(role_slot, ())
    if conflicting:
        conflicting_grade = db.query(Grade.id).filter(
            Grade.task_id == GradingTask.id,
            Grade.grader_user_id == user_id,
            Grade.role_slot.in_(conflicting),
        )
        query = query.filter(~conflicting_grade.exists())

    legacy_labs = legacy_eligible_lab_unit_ids(
        db,
        user_id=user_id,
        disease_id=disease_id,
        capacity=capacity,
        lab_unit_ids=labs,
    )

    package = aliased(EncounterSetGradingPackage)
    query = query.outerjoin(
        package, package.id == GradingTask.encounter_set_package_id
    )
    exact = exact_allocation_predicate(
        GradingTask, package, user_id=user_id, capacity=capacity.value
    )

    legacy_branch = (
        and_(
            GradingTask.project_id.is_(None),
            GradingTask.lab_unit_id.in_(legacy_labs),
        )
        if legacy_labs
        else sa_false()
    )
    return query.filter(
        or_(legacy_branch, and_(GradingTask.project_id.is_not(None), exact))
    )


def _lock_available_candidate(db, task_id: int, role_slot: str):
    """Lock one still-unleased candidate without blocking another grader."""
    active_lease = (
        db.query(GradingWorkbenchSessionTarget.id)
        .join(GradingWorkbenchSession)
        .filter(
            GradingWorkbenchSessionTarget.task_id == GradingTask.id,
            GradingWorkbenchSessionTarget.role_slot == role_slot,
            GradingWorkbenchSessionTarget.released_at.is_(None),
            GradingWorkbenchSession.status == "active",
        )
    )
    return (
        db.query(GradingTask)
        .filter(GradingTask.id == task_id, ~active_lease.exists())
        .with_for_update(skip_locked=True)
        .first()
    )


def select_linked_followup_task(
    db,
    *,
    user_id: int,
    primary_disease_id: int,
    linked_disease_id: int,
    role_slot: str,
):
    labs = eligible_lab_unit_ids(
        db,
        user_id=user_id,
        disease_id=primary_disease_id,
        role_slot=role_slot,
    )
    if not labs:
        return None
    primary_task = aliased(GradingTask)
    linked_task = aliased(GradingTask)
    same_target = or_(
        and_(primary_task.encounter_file_id.isnot(None), primary_task.encounter_file_id == linked_task.encounter_file_id),
        and_(primary_task.direct_image_upload_id.isnot(None), primary_task.direct_image_upload_id == linked_task.direct_image_upload_id),
        and_(primary_task.patient_encounter_id.isnot(None), primary_task.patient_encounter_id == linked_task.patient_encounter_id),
        and_(primary_task.encounter_set_image_id.isnot(None), primary_task.encounter_set_image_id == linked_task.encounter_set_image_id),
    )
    mismatch = (
        and_(primary_task.state.in_(("resident2_done", "final")), linked_task.state == "resident_done")
        if role_slot == "resident2"
        else and_(primary_task.state == "resident_done", linked_task.state == "pending")
    )
    opposite = "resident" if role_slot == "resident2" else "resident2"
    conflicting_grade = db.query(Grade.id).filter(
        Grade.task_id == linked_task.id,
        Grade.grader_user_id == user_id,
        Grade.role_slot == opposite,
    )
    active_lease = (
        db.query(GradingWorkbenchSessionTarget.id)
        .join(GradingWorkbenchSession)
        .filter(
            GradingWorkbenchSessionTarget.task_id == linked_task.id,
            GradingWorkbenchSessionTarget.role_slot == role_slot,
            GradingWorkbenchSessionTarget.released_at.is_(None),
            GradingWorkbenchSession.status == "active",
        )
    )
    query = (
        db.query(linked_task)
        .join(primary_task, same_target)
        .join(
            LinkedDiseaseGrading,
            and_(
                LinkedDiseaseGrading.primary_disease_id == primary_task.disease_id,
                LinkedDiseaseGrading.linked_disease_id == linked_task.disease_id,
                LinkedDiseaseGrading.is_active.is_(True),
            ),
        )
        .filter(
            primary_task.disease_id == primary_disease_id,
            linked_task.disease_id == linked_disease_id,
            primary_task.lab_unit_id.in_(labs),
            mismatch,
            ~conflicting_grade.exists(),
            ~active_lease.exists(),
        )
    )
    for candidate in query.order_by(func.random()).with_for_update(skip_locked=True).yield_per(50):
        if is_user_eligible_for_task(
            db, user_id=user_id, task=candidate, role_slot=role_slot
        ):
            return candidate
    return None


def _exclude_linked_state_mismatches(db, query, disease_id: int):
    linked_ids = get_linked_disease_ids(db, disease_id)
    if not linked_ids:
        return query
    linked_task = aliased(GradingTask)
    same_target = or_(
        and_(GradingTask.encounter_file_id.isnot(None), GradingTask.encounter_file_id == linked_task.encounter_file_id),
        and_(GradingTask.direct_image_upload_id.isnot(None), GradingTask.direct_image_upload_id == linked_task.direct_image_upload_id),
        and_(GradingTask.patient_encounter_id.isnot(None), GradingTask.patient_encounter_id == linked_task.patient_encounter_id),
        and_(GradingTask.encounter_set_image_id.isnot(None), GradingTask.encounter_set_image_id == linked_task.encounter_set_image_id),
    )
    mismatch = or_(
        and_(GradingTask.state == "resident_done", linked_task.state == "pending"),
        and_(GradingTask.state.in_(("resident2_done", "final")), linked_task.state == "resident_done"),
    )
    mismatch_exists = (
        exists()
        .select_from(linked_task)
        .where(same_target)
        .where(linked_task.disease_id.in_(linked_ids))
        .where(
            LinkedDiseaseGrading.primary_disease_id == GradingTask.disease_id,
            LinkedDiseaseGrading.linked_disease_id == linked_task.disease_id,
            LinkedDiseaseGrading.is_active.is_(True),
            mismatch,
        )
    )
    return query.filter(~mismatch_exists)
