"""Atomic next-work selection and durable target leasing."""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from models import EncounterSetGradingPackage, Grade, GradingTask
from utils.dualGradingEligibility import get_user_eligibility_for_task
from .builder import build_workbench
from .configuration import configuration_snapshot
from .errors import ActiveSessionExists, LeaseConflict, NoEligibleWork, WorkbenchAccessDenied
from .models import GradingWorkbenchSession, GradingWorkbenchSessionTarget
from .package_workflow import editable_tasks, ordered_package_tasks, reconcile_package_state
from .linked_tasks import get_linked_disease_ids, get_primary_disease_id
from .queue import select_linked_followup_task, select_next_task
from .sessions import issue_token, new_session_times
from .revisions import is_user_eligible_for_revision


VALID_SLOTS = {"resident", "resident2", "arbitrator"}


def acquire_next(
    db,
    *,
    user_id: int,
    disease_id: int,
    role_slot: str,
    lab_unit_id: int | None = None,
):
    if role_slot not in VALID_SLOTS:
        raise WorkbenchAccessDenied("A valid grading role slot is required.")
    _assert_no_active_session(db, user_id=user_id, role_slot=role_slot)

    primary_disease_id = get_primary_disease_id(db, disease_id)
    if primary_disease_id != disease_id:
        disease_id = primary_disease_id
    candidate, effective_slot = _candidate(
        db, user_id=user_id, disease_id=disease_id, role_slot=role_slot, lab_unit_id=lab_unit_id
    )
    if candidate is None or isinstance(candidate, str):
        raise NoEligibleWork(candidate or "No eligible grading work is currently available.")
    if effective_slot != role_slot:
        _assert_no_active_session(db, user_id=user_id, role_slot=effective_slot)
    return _lease_candidate(
        db,
        candidate=candidate,
        user_id=user_id,
        effective_slot=effective_slot,
        queue_request={"disease_id": disease_id, "lab_unit_id": lab_unit_id, "requested_slot": role_slot},
    )


def acquire_task(db, *, user_id: int, task_uuid: str, role_slot: str):
    if role_slot not in VALID_SLOTS:
        raise WorkbenchAccessDenied("A valid grading role slot is required.")
    _assert_no_active_session(db, user_id=user_id, role_slot=role_slot)
    candidate = (
        db.query(GradingTask)
        .filter(GradingTask.uuid == task_uuid)
        .with_for_update()
        .first()
    )
    if candidate is None:
        raise NoEligibleWork("The requested grading task does not exist.")
    primary_id = get_primary_disease_id(db, candidate.disease_id)
    if primary_id != candidate.disease_id:
        conditions = _same_source_conditions(candidate)
        primary = (
            db.query(GradingTask)
            .filter(GradingTask.disease_id == primary_id, *conditions)
            .with_for_update()
            .first()
        )
        if primary is not None:
            candidate = primary
    if not get_user_eligibility_for_task(db, user_id, candidate.id, role_slot):
        raise WorkbenchAccessDenied("The requested task is outside your grading allocation.")
    if not _state_allows(candidate.state, role_slot):
        raise NoEligibleWork("The requested task is no longer available for this grading slot.")
    return _lease_candidate(
        db,
        candidate=candidate,
        user_id=user_id,
        effective_slot=role_slot,
        queue_request={
            "disease_id": primary_id,
            "lab_unit_id": candidate.lab_unit_id,
            "requested_slot": role_slot,
            "requested_task_uuid": task_uuid,
        },
    )


def acquire_revision(db, *, user_id: int, grade_id: int):
    grade = (
        db.query(Grade)
        .filter(Grade.id == grade_id, Grade.grader_user_id == user_id)
        .with_for_update()
        .first()
    )
    if grade is None:
        raise WorkbenchAccessDenied("The requested grade is unavailable.")
    if grade.role_slot not in VALID_SLOTS:
        raise WorkbenchAccessDenied("This grade cannot be revised in the workbench.")
    _assert_no_active_session(db, user_id=user_id, role_slot=grade.role_slot)
    task = db.query(GradingTask).filter(GradingTask.id == grade.task_id).with_for_update().one()
    eligibility = is_user_eligible_for_revision(
        db, user_id, task.id, grade.role_slot, grade
    )
    if not eligibility.get("eligible"):
        raise WorkbenchAccessDenied(eligibility.get("message") or "This grade is no longer revisable.")
    if not get_user_eligibility_for_task(db, user_id, task.id, grade.role_slot):
        raise WorkbenchAccessDenied("You no longer hold the required grading allocation.")
    return _lease_candidate(
        db,
        candidate=task,
        user_id=user_id,
        effective_slot=grade.role_slot,
        queue_request={
            "disease_id": task.disease_id,
            "lab_unit_id": task.lab_unit_id,
            "requested_slot": grade.role_slot,
            "revision_grade_id": grade.id,
        },
        target_override=[task],
        workflow_override="revision",
    )


def acquire_package(db, *, user_id: int, package_uuid: str, role_slot: str):
    if role_slot not in VALID_SLOTS:
        raise WorkbenchAccessDenied("A valid grading role slot is required.")
    _assert_no_active_session(db, user_id=user_id, role_slot=role_slot)
    package = (
        db.query(EncounterSetGradingPackage)
        .filter(EncounterSetGradingPackage.uuid == package_uuid)
        .with_for_update()
        .first()
    )
    if package is None:
        raise NoEligibleWork("EncounterSet grading package not found.")
    reconcile_package_state(db, package)
    tasks = editable_tasks(package, role_slot, user_id)
    if not tasks:
        raise NoEligibleWork("No targets in this package are editable for the requested slot.")
    for task in tasks:
        if not get_user_eligibility_for_task(db, user_id, task.id, role_slot):
            raise WorkbenchAccessDenied("An EncounterSet package target is outside your grading allocation.")
    return _lease_candidate(
        db,
        candidate=ordered_package_tasks(tasks)[0],
        user_id=user_id,
        effective_slot=role_slot,
        queue_request={
            "disease_id": package.root_scope_disease_id or tasks[0].disease_id,
            "lab_unit_id": tasks[0].lab_unit_id,
            "requested_slot": role_slot,
            "package_uuid": package.uuid,
        },
    )


def acquire_linked_followup(
    db,
    *,
    user_id: int,
    primary_disease_id: int,
    linked_disease_id: int,
):
    for role_slot in ("resident2", "resident"):
        candidate = select_linked_followup_task(
            db,
            user_id=user_id,
            primary_disease_id=primary_disease_id,
            linked_disease_id=linked_disease_id,
            role_slot=role_slot,
        )
        if candidate is None:
            continue
        _assert_no_active_session(db, user_id=user_id, role_slot=role_slot)
        return _lease_candidate(
            db,
            candidate=candidate,
            user_id=user_id,
            effective_slot=role_slot,
            queue_request={
                "disease_id": primary_disease_id,
                "linked_disease_id": linked_disease_id,
                "lab_unit_id": candidate.lab_unit_id,
                "requested_slot": role_slot,
                "linked_followup": True,
            },
            target_override=[candidate],
            workflow_override="linked_followup",
        )
    raise NoEligibleWork("No linked follow-up tasks are currently available.")


def _assert_no_active_session(db, *, user_id, role_slot):
    existing = (
        db.query(GradingWorkbenchSession)
        .filter(
            GradingWorkbenchSession.user_id == user_id,
            GradingWorkbenchSession.role_slot == role_slot,
            GradingWorkbenchSession.status == "active",
        )
        .with_for_update()
        .first()
    )
    if existing is not None:
        raise ActiveSessionExists(
            "Resume or release the active grading session before acquiring another.",
            details={"session_uuid": existing.uuid},
        )


def _lease_candidate(
    db,
    *,
    candidate,
    user_id,
    effective_slot,
    queue_request,
    target_override=None,
    workflow_override=None,
):

    candidate = (
        db.query(GradingTask)
        .filter(GradingTask.id == candidate.id)
        .with_for_update()
        .one()
    )
    if target_override is None:
        tasks, workflow = _target_group(db, candidate=candidate, user_id=user_id, role_slot=effective_slot)
    else:
        tasks, workflow = target_override, workflow_override
    tasks = _lock_tasks(db, tasks)
    snapshot, fingerprint = configuration_snapshot(
        db, tasks=tasks, workflow=workflow, role_slot=effective_slot
    )
    raw_token, token_hash = issue_token()
    acquired_at, idle_expires_at, absolute_expires_at = new_session_times()
    session = GradingWorkbenchSession(
        user_id=user_id,
        role_slot=effective_slot,
        workflow=workflow,
        root_task_id=candidate.id,
        encounter_set_package_id=candidate.encounter_set_package_id,
        token_hash=token_hash,
        configuration_snapshot_json=snapshot,
        configuration_fingerprint=fingerprint,
        queue_request_json=queue_request,
        acquired_at=acquired_at,
        last_heartbeat_at=acquired_at,
        idle_expires_at=idle_expires_at,
        absolute_expires_at=absolute_expires_at,
    )
    db.add(session)
    db.flush()
    for order, task in enumerate(tasks):
        target_purpose = _target_purpose(
            task_state=task.state,
            role_slot=effective_slot,
            workflow=workflow,
        )
        grade = _current_grade(db, task_id=task.id, user_id=user_id, role_slot=effective_slot)
        session.targets.append(GradingWorkbenchSessionTarget(
            task_id=task.id,
            role_slot=effective_slot,
            target_order=order,
            target_purpose=target_purpose,
            acquired_task_state=task.state,
            acquired_grade_updated_at=grade.updated_at if grade else None,
            acquired_at=acquired_at,
        ))
    try:
        db.flush()
    except IntegrityError as exc:
        raise LeaseConflict("This grading work was acquired by another grader.") from exc
    return build_workbench(db, session, tasks), raw_token


def _candidate(db, *, user_id, disease_id, role_slot, lab_unit_id):
    if role_slot == "resident":
        candidate = select_next_task(
            db, user_id=user_id, disease_id=disease_id, role_slot="resident2", lab_unit_id=lab_unit_id
        )
        if candidate is not None:
            return candidate, "resident2"
        return select_next_task(
            db, user_id=user_id, disease_id=disease_id, role_slot="resident", lab_unit_id=lab_unit_id
        ), "resident"
    if role_slot == "resident2":
        candidate = select_next_task(
            db, user_id=user_id, disease_id=disease_id, role_slot="resident2", lab_unit_id=lab_unit_id
        )
        if candidate is not None:
            return candidate, "resident2"
        return select_next_task(
            db, user_id=user_id, disease_id=disease_id, role_slot="resident", lab_unit_id=lab_unit_id
        ), "resident"
    return select_next_task(
        db, user_id=user_id, disease_id=disease_id, role_slot="arbitrator", lab_unit_id=lab_unit_id
    ), "arbitrator"


def _target_group(db, *, candidate, user_id, role_slot):
    if candidate.encounter_set_package_id and candidate.encounter_set_package:
        package = candidate.encounter_set_package
        reconcile_package_state(db, package)
        tasks = editable_tasks(package, role_slot, user_id)
        if not tasks:
            raise NoEligibleWork("No targets in this package are editable for the requested slot.")
        for task in tasks:
            if not get_user_eligibility_for_task(db, user_id, task.id, role_slot):
                raise WorkbenchAccessDenied("An EncounterSet package target is outside your grading allocation.")
        return ordered_package_tasks(tasks), "package"

    linked_ids = get_linked_disease_ids(db, candidate.disease_id)
    if not linked_ids:
        return [candidate], "ordinary"
    conditions = _same_source_conditions(candidate)
    tasks = (
        db.query(GradingTask)
        .filter(GradingTask.disease_id.in_([candidate.disease_id, *linked_ids]), *conditions)
        .order_by(GradingTask.id)
        .all()
    )
    visible = [
        task for task in tasks
        if get_user_eligibility_for_task(db, user_id, task.id, role_slot)
    ]
    return (visible or [candidate]), "linked"


def _same_source_conditions(task):
    for column_name in (
        "encounter_file_id",
        "direct_image_upload_id",
        "patient_encounter_id",
        "encounter_set_image_id",
    ):
        value = getattr(task, column_name)
        if value is not None:
            return [getattr(GradingTask, column_name) == value]
    return [GradingTask.id == task.id]


def _state_allows(state: str, slot: str) -> bool:
    return state == {"resident": "pending", "resident2": "resident_done", "arbitrator": "arbitration"}[slot]


def _target_purpose(*, task_state: str, role_slot: str, workflow: str) -> str:
    # Revision-window package targets and explicit single-grade revisions are
    # intentionally editable after their normal queue state has advanced.
    if workflow in {"package", "revision"}:
        return "editable"
    return "editable" if _state_allows(task_state, role_slot) else "evidence"


def _lock_tasks(db, tasks):
    ordered_ids = [task.id for task in tasks]
    ids = sorted(ordered_ids)
    locked = db.query(GradingTask).filter(GradingTask.id.in_(ids)).order_by(GradingTask.id).with_for_update().all()
    by_id = {task.id: task for task in locked}
    return [by_id[item] for item in ordered_ids]


def _current_grade(db, *, task_id, user_id, role_slot):
    return (
        db.query(Grade)
        .filter(Grade.task_id == task_id, Grade.grader_user_id == user_id, Grade.role_slot == role_slot)
        .first()
    )
