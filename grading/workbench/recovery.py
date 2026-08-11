"""Recovery of incomplete EncounterSet package grading stages."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.orm import selectinload

from auth.utils import utcnow
from models import (
    AnnotationSet,
    EncounterSetGradingPackage,
    EncounterSetGradingSubmission,
    Grade,
    GradingTask,
)

from .audit import snapshot_grade
from .models import (
    GradingSubmissionEvent,
    GradingSubmissionEventItem,
    GradingWorkbenchSession,
)
from .package_workflow import (
    HUMAN_ROLE_SLOTS,
    complete_package_submission,
    reconcile_package_state,
)
from .sources import resolve_task_source


PACKAGE_ALLOCATION_WINDOW = timedelta(minutes=30)
_PRECEDING_SLOT = {"resident2": "resident", "arbitrator": "resident2"}


@dataclass(frozen=True)
class IncompletePackageRecoveryResult:
    expired_session_count: int = 0
    reset_package_count: int = 0
    reset_grade_count: int = 0


def recover_incomplete_package_stages(
    db,
    *,
    now=None,
) -> IncompletePackageRecoveryResult:
    """Invalidate premature stages and reset partial package grades after 30 minutes."""
    now = now or utcnow()
    complete_submission_exists = (
        db.query(EncounterSetGradingSubmission.id)
        .filter(
            EncounterSetGradingSubmission.encounter_set_package_id
            == GradingTask.encounter_set_package_id,
            EncounterSetGradingSubmission.role_slot == Grade.role_slot,
            EncounterSetGradingSubmission.is_complete.is_(True),
        )
        .exists()
    )
    package_ids = {
        package_id
        for (package_id,) in (
            db.query(GradingTask.encounter_set_package_id)
            .join(Grade, Grade.task_id == GradingTask.id)
            .filter(
                GradingTask.encounter_set_package_id.is_not(None),
                Grade.role_slot.in_(HUMAN_ROLE_SLOTS),
                ~complete_submission_exists,
            )
            .distinct()
            .all()
        )
    }
    active_package_ids = {
        package_id
        for (package_id,) in (
            db.query(GradingWorkbenchSession.encounter_set_package_id)
            .filter(
                GradingWorkbenchSession.workflow == "package",
                GradingWorkbenchSession.status == "active",
                GradingWorkbenchSession.encounter_set_package_id.is_not(None),
            )
            .distinct()
            .all()
        )
    }
    package_ids.update(active_package_ids)
    if not package_ids:
        return IncompletePackageRecoveryResult()

    packages = (
        db.query(EncounterSetGradingPackage)
        .options(
            selectinload(EncounterSetGradingPackage.tasks).selectinload(GradingTask.grades),
            selectinload(EncounterSetGradingPackage.submissions).selectinload(
                EncounterSetGradingSubmission.items
            ),
            selectinload(EncounterSetGradingPackage.scopes),
        )
        .filter(EncounterSetGradingPackage.id.in_(package_ids))
        .order_by(EncounterSetGradingPackage.id)
        .populate_existing()
        .with_for_update()
        .all()
    )
    sessions = (
        db.query(GradingWorkbenchSession)
        .options(selectinload(GradingWorkbenchSession.targets))
        .filter(GradingWorkbenchSession.encounter_set_package_id.in_(package_ids))
        .order_by(GradingWorkbenchSession.acquired_at, GradingWorkbenchSession.id)
        .all()
    )
    sessions_by_package: dict[int, list[GradingWorkbenchSession]] = {}
    for session in sessions:
        sessions_by_package.setdefault(session.encounter_set_package_id, []).append(session)

    expired_session_count = 0
    reset_package_count = 0
    reset_grade_count = 0
    for package in packages:
        package_sessions = sessions_by_package.get(package.id, [])
        for session in package_sessions:
            preceding_slot = _PRECEDING_SLOT.get(session.role_slot)
            if (
                session.status == "active"
                and preceding_slot is not None
                and complete_package_submission(package, preceding_slot) is None
            ):
                _close_session(
                    session,
                    status="invalidated",
                    reason="incomplete_preceding_package_stage",
                    now=now,
                )
                expired_session_count += 1

        package_reset = False
        for role_slot in ("resident", "resident2", "arbitrator"):
            if complete_package_submission(package, role_slot) is not None:
                continue
            grades = [
                grade
                for task in package.tasks
                for grade in task.grades
                if grade.role_slot == role_slot
            ]
            if not grades:
                continue
            allocation_start = _initial_allocation_time(
                package_sessions=package_sessions,
                role_slot=role_slot,
                grades=grades,
            )
            if allocation_start + PACKAGE_ALLOCATION_WINDOW > now:
                continue

            same_slot_sessions = [
                session
                for session in package_sessions
                if session.role_slot == role_slot and session.status == "active"
            ]
            for session in same_slot_sessions:
                _close_session(
                    session,
                    status="expired",
                    reason="incomplete_package_stage_expired",
                    now=now,
                )
                expired_session_count += 1

            _audit_and_remove_grades(
                db,
                package=package,
                role_slot=role_slot,
                grades=grades,
                allocation_start=allocation_start,
                deadline=allocation_start + PACKAGE_ALLOCATION_WINDOW,
                session=same_slot_sessions[0] if same_slot_sessions else None,
            )
            reset_grade_count += len(grades)
            package_reset = True
            owner_attr = f"{role_slot}_user_id"
            setattr(package, owner_attr, None)

        if package_reset:
            db.flush()
            revision_before = package.revision_number
            reconcile_package_state(db, package, now=now)
            if package.revision_number == revision_before:
                package.revision_number += 1
            reset_package_count += 1

    if expired_session_count or reset_package_count:
        db.flush()
    return IncompletePackageRecoveryResult(
        expired_session_count=expired_session_count,
        reset_package_count=reset_package_count,
        reset_grade_count=reset_grade_count,
    )


def _initial_allocation_time(*, package_sessions, role_slot: str, grades: list[Grade]):
    owner_ids = {grade.grader_user_id for grade in grades}
    session_times = [
        session.acquired_at
        for session in package_sessions
        if session.role_slot == role_slot and session.user_id in owner_ids
    ]
    return min(session_times or [grade.created_at for grade in grades])


def _audit_and_remove_grades(
    db,
    *,
    package,
    role_slot: str,
    grades: list[Grade],
    allocation_start,
    deadline,
    session,
) -> None:
    grades_by_user: dict[int, list[Grade]] = {}
    for grade in grades:
        grades_by_user.setdefault(grade.grader_user_id, []).append(grade)
    tasks_by_id = {task.id: task for task in package.tasks}
    for grader_user_id, user_grades in grades_by_user.items():
        first_task = tasks_by_id[user_grades[0].task_id]
        source = resolve_task_source(db, first_task).source
        event = GradingSubmissionEvent(
            actor_user_id=grader_user_id,
            role_slot=role_slot,
            workflow="package",
            action="expire_incomplete_package",
            outcome="accepted",
            result_code="partial_grades_reset",
            session_id=session.id if session and session.user_id == grader_user_id else None,
            root_task_id=first_task.id,
            encounter_set_package_id=package.id,
            project_id=source.project_id,
            lab_unit_id=source.lab_unit_id,
            source_profile_id=source.profile_id,
            source_lineage=source.profile_lineage,
            diagnostic_metadata_json={
                "allocation_started_at": allocation_start.isoformat(),
                "allocation_expired_at": deadline.isoformat(),
                "removed_grade_ids": [grade.id for grade in user_grades],
            },
        )
        db.add(event)
        db.flush()
        for grade in user_grades:
            task = tasks_by_id[grade.task_id]
            annotation_set = (
                db.query(AnnotationSet).filter(AnnotationSet.grade_id == grade.id).first()
            )
            event.items.append(
                GradingSubmissionEventItem(
                    task_id=task.id,
                    grade_id=grade.id,
                    disease_id=task.disease_id,
                    target_level=task.grading_target_level,
                    grade_revision=1,
                    before_json=snapshot_grade(grade, task_state=task.state),
                    after_json={
                        "removed": True,
                        "reason": "incomplete_package_stage_expired",
                    },
                    annotation_set_uuid=annotation_set.uuid if annotation_set else None,
                )
            )
            task.grades.remove(grade)
            db.delete(grade)


def _close_session(session, *, status: str, reason: str, now) -> None:
    session.status = status
    session.close_reason = reason
    if status == "invalidated":
        session.invalidated_at = now
    else:
        session.released_at = now
    for target in session.targets:
        if target.released_at is None:
            target.released_at = now
            target.release_reason = reason
