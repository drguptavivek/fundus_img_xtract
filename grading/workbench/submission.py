"""Common workbench submission orchestration."""

from __future__ import annotations

import json

from .package_workflow import (
    EncounterSetSubmissionInputDTO,
    TargetGradeInputDTO,
    submit_package,
)
from models import DiseaseGrading, Grade, GradingTask
from .annotations import parse_grade_observation, persist_grade_annotations
from .audit import accepted_event, snapshot_grade
from .configuration import configuration_snapshot
from .errors import ConfigurationChanged, LeaseConflict, SessionExpired, WorkbenchError
from .models import GradingSubmissionEvent, GradingWorkbenchSession
from .sessions import _assert_access, _close, _tasks_for_session, _verify_active, _verify_token
from .state import apply_grade_state


class TargetSetMismatch(WorkbenchError):
    code = "target_set_mismatch"
    status_code = 409
    reload_required = True


class IncompleteSubmission(WorkbenchError):
    code = "incomplete_submission"


def submit(
    db,
    *,
    session_uuid: str,
    user_id: int,
    raw_token: str,
    token_generation: int,
    payload: dict,
):
    idempotency_key = str(payload.get("idempotency_key") or "").strip()
    if not idempotency_key or len(idempotency_key) > 64:
        raise IncompleteSubmission("A valid idempotency_key is required.")
    session = (
        db.query(GradingWorkbenchSession)
        .filter(GradingWorkbenchSession.uuid == session_uuid)
        .with_for_update()
        .first()
    )
    if session is None or session.user_id != user_id:
        raise SessionExpired("The grading session is unavailable.")
    prior = (
        db.query(GradingSubmissionEvent)
        .filter(
            GradingSubmissionEvent.session_id == session.id,
            GradingSubmissionEvent.idempotency_key == idempotency_key,
            GradingSubmissionEvent.outcome == "accepted",
        )
        .first()
    )
    if prior is not None:
        return {"event_uuid": prior.uuid, "idempotent_replay": True, "queue_request": session.queue_request_json}
    _verify_active(session)
    _verify_token(session, raw_token=raw_token, token_generation=token_generation)
    all_tasks = _tasks_for_session(db, session, for_update=True)
    _assert_access(db, session=session, tasks=all_tasks, user_id=user_id)
    tasks = _editable_tasks(session, all_tasks)
    _assert_targets_unchanged(db, session=session, tasks=tasks, user_id=user_id)

    snapshot, fingerprint = configuration_snapshot(
        db,
        tasks=all_tasks,
        workflow=session.workflow,
        role_slot=session.role_slot,
    )
    if payload.get("configuration_fingerprint") != session.configuration_fingerprint or fingerprint != session.configuration_fingerprint:
        raise ConfigurationChanged("Grading configuration changed. Reload before submitting.")
    observations_payload = payload.get("observations")
    if not isinstance(observations_payload, dict):
        raise IncompleteSubmission("Submission observations are required.")
    expected = {task.uuid for task in tasks}
    if set(observations_payload) != expected:
        raise TargetSetMismatch("The submitted task set does not match the leased workbench.")

    before: dict[int, dict | None] = {}
    observations = {}
    for task in tasks:
        target = observations_payload[task.uuid]
        if not isinstance(target, dict):
            raise IncompleteSubmission("Every target observation must be an object.")
        existing = _grade(db, task=task, user_id=user_id, role_slot=session.role_slot)
        before[task.id] = snapshot_grade(existing, task_state=task.state)
        geometry_value = target.get("feature_geometry")
        raw_geometry = None
        if "feature_geometry" in target:
            raw_geometry = "" if geometry_value is None else json.dumps(geometry_value)
        try:
            label_id = int(target.get("disease_grading_id"))
        except (TypeError, ValueError) as exc:
            raise IncompleteSubmission("Every target requires a valid disease grade.") from exc
        observations[task.id] = parse_grade_observation(
            db,
            task=task,
            label_id=label_id,
            comment=target.get("comment"),
            raw_selected_features=[str(item) for item in (target.get("selected_feature_ids") or [])],
            raw_feature_geometry=raw_geometry,
            submitted_policy_revision=target.get("annotation_policy_revision"),
            existing_grade=existing,
        )

    specialized = None
    if session.workflow == "package":
        try:
            package_revision = int(payload.get("package_revision"))
        except (TypeError, ValueError) as exc:
            raise IncompleteSubmission("A valid package_revision is required.") from exc
        specialized = submit_package(db, tasks[0].encounter_set_package, EncounterSetSubmissionInputDTO(
            package_uuid=tasks[0].encounter_set_package.uuid,
            role_slot=session.role_slot,
            grader_user_id=user_id,
            expected_package_revision=package_revision,
            targets=tuple(
                TargetGradeInputDTO(
                    task_uuid=task.uuid,
                    disease_grading_id=observations[task.id].disease_grading_id,
                    comment=observations[task.id].comment,
                    selected_features_json=observations[task.id].selected_features_json,
                    feature_geometry_json=observations[task.id].feature_geometry_json,
                )
                for task in tasks
            ),
        ))
    else:
        for task in tasks:
            _write_ordinary_grade(
                db, task=task, user_id=user_id, role_slot=session.role_slot, observation=observations[task.id]
            )
        for task in tasks:
            apply_grade_state(db, task=task)

    grades = {task.id: _grade(db, task=task, user_id=user_id, role_slot=session.role_slot) for task in tasks}
    annotation_uuids: dict[int, str] = {}
    for task in tasks:
        annotation_set = persist_grade_annotations(
            db, grade=grades[task.id], task=task, observation=observations[task.id]
        )
        annotation_uuids[task.id] = annotation_set.uuid
    event = accepted_event(
        db,
        session=session,
        tasks=tasks,
        actor_user_id=user_id,
        action=str(payload.get("action") or "save_close"),
        idempotency_key=idempotency_key,
        before_by_task_id=before,
        grades_by_task_id=grades,
        annotation_set_uuid_by_task_id=annotation_uuids,
        specialized_record_type="encounter_set_submission" if specialized else None,
        specialized_record_id=specialized.id if specialized else None,
    )
    _close(session, status="completed", reason="submitted")
    db.flush()
    return {"event_uuid": event.uuid, "idempotent_replay": False, "queue_request": session.queue_request_json}


def _write_ordinary_grade(db, *, task, user_id, role_slot, observation):
    label = db.get(DiseaseGrading, observation.disease_grading_id)
    grade = _grade(db, task=task, user_id=user_id, role_slot=role_slot)
    if grade is None:
        grade = Grade(task_id=task.id, grader_user_id=user_id, role_slot=role_slot, disease_grading_id=label.id)
        db.add(grade)
    grade.disease_grading_id = label.id
    grade.comment = observation.comment
    grade.selected_features_json = observation.selected_features_json
    grade.feature_geometry_json = observation.feature_geometry_json
    grade.disease_name = task.disease.name
    grade.grade_name = label.impression
    grade.grade_description = label.guidelines
    db.flush()
    return grade


def _grade(db, *, task, user_id, role_slot):
    return (
        db.query(Grade)
        .filter(Grade.task_id == task.id, Grade.grader_user_id == user_id, Grade.role_slot == role_slot)
        .first()
    )


def _assert_targets_unchanged(db, *, session, tasks, user_id):
    targets = {item.task_id: item for item in session.targets}
    for task in tasks:
        target = targets[task.id]
        if target.released_at is not None:
            raise SessionExpired("A grading target in this session was released.")
        if task.state != target.acquired_task_state:
            raise ConfigurationChanged("A grading target changed after acquisition. Reload before submitting.")
        grade = _grade(db, task=task, user_id=user_id, role_slot=session.role_slot)
        current_updated_at = grade.updated_at if grade else None
        if current_updated_at != target.acquired_grade_updated_at:
            raise LeaseConflict("Your grade was revised after this workbench was acquired.")


def _editable_tasks(session, tasks):
    purpose_by_task_id = {item.task_id: item.target_purpose for item in session.targets}
    return [task for task in tasks if purpose_by_task_id.get(task.id) == "editable"]
