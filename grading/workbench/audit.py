"""Unified append-only grading submission history."""

from __future__ import annotations

from models import Grade, GradingTask

from .models import GradingSubmissionEvent, GradingSubmissionEventItem
from .models import GradingWorkbenchSession
from .sources import resolve_task_source


def snapshot_grade(grade: Grade | None, *, task_state: str) -> dict | None:
    if grade is None:
        return None
    return {
        "grade_id": grade.id,
        "task_state": task_state,
        "disease_grading_id": grade.disease_grading_id,
        "grade_name": grade.grade_name,
        "comment": grade.comment,
        "selected_features_json": grade.selected_features_json,
        "feature_geometry_json": grade.feature_geometry_json,
        "grader_user_id": grade.grader_user_id,
        "role_slot": grade.role_slot,
        "created_at": grade.created_at.isoformat() if grade.created_at else None,
        "updated_at": grade.updated_at.isoformat() if grade.updated_at else None,
    }


def accepted_event(
    db,
    *,
    session,
    tasks: list[GradingTask],
    actor_user_id: int,
    action: str,
    idempotency_key: str,
    before_by_task_id: dict[int, dict | None],
    grades_by_task_id: dict[int, Grade],
    annotation_set_uuid_by_task_id: dict[int, str | None],
    specialized_record_type: str | None = None,
    specialized_record_id: int | None = None,
):
    first_source = resolve_task_source(db, tasks[0]).source
    target_snapshots = {
        item["task_uuid"]: item
        for item in (session.configuration_snapshot_json or {}).get("targets", [])
    }
    event = GradingSubmissionEvent(
        actor_user_id=actor_user_id,
        role_slot=session.role_slot,
        workflow=session.workflow,
        action=action,
        outcome="accepted",
        result_code="accepted",
        session_id=session.id,
        root_task_id=session.root_task_id,
        encounter_set_package_id=session.encounter_set_package_id,
        project_id=first_source.project_id,
        lab_unit_id=first_source.lab_unit_id,
        source_profile_id=first_source.profile_id,
        source_lineage=first_source.profile_lineage,
        configuration_fingerprint=session.configuration_fingerprint,
        policy_revisions_json={
            task.uuid: target_snapshots[task.uuid]["annotation_policy_revision"]
            for task in tasks
        },
        idempotency_key=idempotency_key,
        specialized_record_type=specialized_record_type,
        specialized_record_id=specialized_record_id,
    )
    db.add(event)
    db.flush()
    for task in tasks:
        grade = grades_by_task_id[task.id]
        prior_count = (
            db.query(GradingSubmissionEventItem)
            .join(GradingSubmissionEvent)
            .filter(
                GradingSubmissionEventItem.grade_id == grade.id,
                GradingSubmissionEvent.outcome == "accepted",
            )
            .count()
        )
        event.items.append(GradingSubmissionEventItem(
            task_id=task.id,
            grade_id=grade.id,
            disease_id=task.disease_id,
            target_level=task.grading_target_level or ("encounter" if task.patient_encounter_id else "image"),
            grade_revision=prior_count + 1,
            before_json=before_by_task_id.get(task.id),
            after_json=snapshot_grade(grade, task_state=task.state),
            annotation_set_uuid=annotation_set_uuid_by_task_id.get(task.id),
        ))
    db.flush()
    return event


def rejected_event(
    db,
    *,
    actor_user_id: int,
    role_slot: str,
    workflow: str,
    result_code: str,
    session_id: int | None = None,
    diagnostic_metadata: dict | None = None,
):
    row = GradingSubmissionEvent(
        actor_user_id=actor_user_id,
        role_slot=role_slot or "resident",
        workflow=workflow or "unknown",
        action="submit",
        outcome="conflict" if result_code.endswith("conflict") or result_code.endswith("changed") else "rejected",
        result_code=result_code,
        session_id=session_id,
        diagnostic_metadata_json=diagnostic_metadata or {},
    )
    db.add(row)
    db.flush()
    return row


def record_rejected_submission(
    db,
    *,
    actor_user_id: int,
    session_uuid: str,
    result_code: str,
    action: str | None,
):
    session = (
        db.query(GradingWorkbenchSession)
        .filter(GradingWorkbenchSession.uuid == session_uuid)
        .first()
    )
    row = rejected_event(
        db,
        actor_user_id=actor_user_id,
        role_slot=session.role_slot if session else "resident",
        workflow=session.workflow if session else "unknown",
        result_code=result_code,
        session_id=session.id if session else None,
        diagnostic_metadata={
            "session_uuid": session_uuid,
            "action": action,
        },
    )
    return row
