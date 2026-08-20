"""Guard and snapshot helpers for reopening a verified EncounterSet."""
from __future__ import annotations

from models import EncounterSetGradingPackage, EncounterSetImage, Grade, GradingTask, PatientEncounters, User

# Grade.role_slot values: 'resident' | 'resident2' | 'arbitrator' | 'ai' | 'review'.
# Only human work should block a reopen - 'ai' grades are automated and cheap to
# regenerate (same reasoning already applied to AIInferenceRun), and state transitions
# (pending -> resident_done -> ...) are themselves only ever driven by these same three
# roles, so an 'ai'-only grade leaves state at 'pending' by design, not by accident.
HUMAN_GRADE_ROLE_SLOTS = ("resident", "resident2", "arbitrator", "review")


def check_reopen_guard(db, encounter: PatientEncounters) -> list[dict]:
    """Return descriptors for grading tasks blocking a reopen; empty means safe."""
    encounter_task_ids = [
        row[0]
        for row in db.query(GradingTask.id)
        .filter(GradingTask.patient_encounter_id == encounter.id)
        .all()
    ]
    image_task_ids = [
        row[0]
        for row in db.query(GradingTask.id)
        .join(EncounterSetImage, GradingTask.encounter_set_image_id == EncounterSetImage.id)
        .filter(EncounterSetImage.patient_encounter_id == encounter.id)
        .all()
    ]
    all_task_ids = encounter_task_ids + image_task_ids
    if not all_task_ids:
        return []

    tasks_by_id = {
        task.id: task
        for task in db.query(GradingTask).filter(GradingTask.id.in_(all_task_ids)).all()
    }
    graded_task_ids = {
        row[0]
        for row in db.query(Grade.task_id)
        .filter(
            Grade.task_id.in_(all_task_ids),
            Grade.role_slot.in_(HUMAN_GRADE_ROLE_SLOTS),
        )
        .distinct()
        .all()
    }

    blockers: list[dict] = []
    for task_id, task in tasks_by_id.items():
        if task.state != "pending":
            blockers.append({
                "task_uuid": task.uuid,
                "state": task.state,
                "disease_id": task.disease_id,
                "reason": "state_progressed",
            })
        elif task_id in graded_task_ids:
            blockers.append({
                "task_uuid": task.uuid,
                "state": task.state,
                "disease_id": task.disease_id,
                "reason": "has_grades",
            })
    return blockers


def snapshot_encounter(db, encounter: PatientEncounters) -> dict:
    """Column-level before/after snapshot for the verification history audit row."""
    packages = (
        db.query(EncounterSetGradingPackage)
        .filter_by(patient_encounter_id=encounter.id)
        .all()
    )
    assignee_ids = {
        user_id
        for package in packages
        for user_id in (
            package.resident_user_id,
            package.resident2_user_id,
            package.arbitrator_user_id,
        )
        if user_id
    }
    assignee_usernames = sorted(
        username
        for (username,) in db.query(User.username).filter(User.id.in_(assignee_ids)).all()
    ) if assignee_ids else []
    return {
        "encounter_verified_status": encounter.encounter_verified_status,
        "encounter_verified_by": encounter.encounter_verified_by,
        "encounter_verified_at": (
            encounter.encounter_verified_at.isoformat() if encounter.encounter_verified_at else None
        ),
        "referral_suggestion": encounter.referral_suggestion,
        "referral_positive_diseases_json": list(encounter.referral_positive_diseases_json or []),
        "metadata_json": dict(encounter.metadata_json or {}),
        "grading_package_assignees": assignee_usernames,
    }
