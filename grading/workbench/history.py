"""Detached serializers for the unified grading revision history."""

from __future__ import annotations

from .models import GradingSubmissionEvent


def submission_history(db, *, actor_user_id: int, limit: int = 50) -> list[dict[str, object]]:
    limit = min(max(int(limit), 1), 200)
    events = (
        db.query(GradingSubmissionEvent)
        .filter(GradingSubmissionEvent.actor_user_id == actor_user_id)
        .order_by(GradingSubmissionEvent.created_at.desc(), GradingSubmissionEvent.id.desc())
        .limit(limit)
        .all()
    )
    return [_event_dto(event) for event in events]


def _event_dto(event) -> dict[str, object]:
    return {
        "event_uuid": event.uuid,
        "workflow": event.workflow,
        "role_slot": event.role_slot,
        "action": event.action,
        "outcome": event.outcome,
        "result_code": event.result_code,
        "session_uuid": event.session.uuid if event.session else None,
        "package_id": event.encounter_set_package_id,
        "project_id": event.project_id,
        "lab_unit_id": event.lab_unit_id,
        "source_profile_id": event.source_profile_id,
        "source_lineage": event.source_lineage,
        "configuration_fingerprint": event.configuration_fingerprint,
        "policy_revisions": event.policy_revisions_json or {},
        "specialized_record": {
            "type": event.specialized_record_type,
            "id": event.specialized_record_id,
        } if event.specialized_record_type else None,
        "created_at": event.created_at.isoformat(),
        "items": [
            {
                "task_id": item.task_id,
                "grade_id": item.grade_id,
                "disease_id": item.disease_id,
                "target_level": item.target_level,
                "grade_revision": item.grade_revision,
                "before": item.before_json,
                "after": item.after_json,
                "annotation_set_uuid": item.annotation_set_uuid,
            }
            for item in sorted(event.items, key=lambda value: value.id)
        ],
    }
