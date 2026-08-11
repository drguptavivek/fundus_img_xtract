"""Authoritative next-task selection for the grading workbench.

The durable session-target lease is the concurrency boundary.  This module
does not create or consult the legacy ``TaskTracker`` rows.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import and_, exists, func, or_
from sqlalchemy.orm import aliased, joinedload

from grading_allocation.eligibility import (
    eligible_enforced_project_task_contexts,
    eligible_lab_unit_ids,
    is_user_eligible_for_task,
)
from grading_allocation.exceptions import AllocationContextError
from grading_allocation.models import ProjectGradingAllocationPolicy
from grading_allocation.resolver import resolve_task_allocation_context
from models import EncounterFile, EncounterSetImage, Grade, GradingTask, LinkedDiseaseGrading
from .models import GradingWorkbenchSession, GradingWorkbenchSessionTarget
from .package_workflow import reconcile_active_packages
from .linked_tasks import get_linked_disease_ids
from auth.utils import utcnow


def select_next_task(db, *, user_id: int, disease_id: int, role_slot: str, lab_unit_id: int | None):
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

    # Resolve project allocation in bulk. Calling the scalar eligibility
    # service for every ineligible row made an empty Resident2 queue take tens
    # of seconds before Save & Next could fall back to Resident work.
    candidates = (
        query.options(
            joinedload(GradingTask.encounter_file).joinedload(EncounterFile.patient_encounter),
            joinedload(GradingTask.direct_image),
            joinedload(GradingTask.patient_encounter),
            joinedload(GradingTask.encounter_set_image).joinedload(EncounterSetImage.patient_encounter),
            joinedload(GradingTask.encounter_set_package),
        )
        .order_by(func.random())
        .all()
    )
    enforced_project_ids = {
        row[0]
        for row in db.query(ProjectGradingAllocationPolicy.project_id)
        .filter(ProjectGradingAllocationPolicy.enforcement_enabled.is_(True))
        .all()
    }
    enforced_eligible = eligible_enforced_project_task_contexts(
        db,
        user_id=user_id,
        task_slots=[(candidate, role_slot) for candidate in candidates],
        enforced_project_ids=enforced_project_ids,
    )
    legacy_allowed_by_lab: dict[int, bool] = {}
    for candidate in candidates:
        try:
            context = resolve_task_allocation_context(db, candidate)
        except AllocationContextError:
            continue
        if context.project_id in enforced_project_ids:
            if (candidate.id, role_slot) in enforced_eligible:
                locked = _lock_available_candidate(db, candidate.id, role_slot)
                if locked is not None:
                    return locked
            continue
        if role_slot in {"resident", "resident2"}:
            # The SQL queue already excludes the opposite resident slot. The
            # remaining legacy decision depends only on this queue's user,
            # disease, lab and capacity, so evaluate it once rather than once
            # for thousands of tasks from the same queue.
            if candidate.lab_unit_id not in legacy_allowed_by_lab:
                legacy_allowed_by_lab[candidate.lab_unit_id] = is_user_eligible_for_task(
                    db, user_id=user_id, task=candidate, role_slot=role_slot
                )
            if legacy_allowed_by_lab[candidate.lab_unit_id]:
                locked = _lock_available_candidate(db, candidate.id, role_slot)
                if locked is not None:
                    return locked
            continue
        if is_user_eligible_for_task(
            db, user_id=user_id, task=candidate, role_slot=role_slot
        ):
            locked = _lock_available_candidate(db, candidate.id, role_slot)
            if locked is not None:
                return locked
    return None


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
