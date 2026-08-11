"""Narrow public façade for the consolidated grading workbench."""

from __future__ import annotations

from .acquisition import (
    acquire_linked_followup,
    acquire_next,
    acquire_package,
    acquire_revision,
    acquire_task,
)
from .sessions import expire_stale, heartbeat, list_active, load, release, resume
from .submission import submit
from .drafts import save_draft
from .history import submission_history
from .audit import record_rejected_submission as _record_rejected_submission


def list_active_sessions(db, *, user_id: int):
    return list_active(db, user_id=user_id)


def get_submission_history(db, *, user_id: int, limit: int = 50):
    return submission_history(db, actor_user_id=user_id, limit=limit)


def record_rejected_workbench_submission(db, *, user_id: int, session_uuid: str, result_code: str, action: str | None):
    return _record_rejected_submission(
        db,
        actor_user_id=user_id,
        session_uuid=session_uuid,
        result_code=result_code,
        action=action,
    )


def acquire_next_workbench(db, *, user_id: int, disease_id: int, role_slot: str, lab_unit_id: int | None = None):
    return acquire_next(
        db,
        user_id=user_id,
        disease_id=disease_id,
        role_slot=role_slot,
        lab_unit_id=lab_unit_id,
    )


def acquire_task_workbench(db, *, user_id: int, task_uuid: str, role_slot: str):
    return acquire_task(
        db, user_id=user_id, task_uuid=task_uuid, role_slot=role_slot
    )


def acquire_revision_workbench(db, *, user_id: int, grade_id: int):
    return acquire_revision(db, user_id=user_id, grade_id=grade_id)


def acquire_package_workbench(db, *, user_id: int, package_uuid: str, role_slot: str):
    return acquire_package(
        db, user_id=user_id, package_uuid=package_uuid, role_slot=role_slot
    )


def acquire_linked_followup_workbench(db, *, user_id: int, primary_disease_id: int, linked_disease_id: int):
    return acquire_linked_followup(
        db,
        user_id=user_id,
        primary_disease_id=primary_disease_id,
        linked_disease_id=linked_disease_id,
    )


def load_workbench(db, *, session_uuid: str, user_id: int, raw_token: str, token_generation: int):
    return load(
        db,
        session_uuid=session_uuid,
        user_id=user_id,
        raw_token=raw_token,
        token_generation=token_generation,
    )


def resume_workbench(db, *, session_uuid: str, user_id: int):
    return resume(db, session_uuid=session_uuid, user_id=user_id)


def heartbeat_workbench(db, *, session_uuid: str, user_id: int, raw_token: str, token_generation: int):
    return heartbeat(
        db,
        session_uuid=session_uuid,
        user_id=user_id,
        raw_token=raw_token,
        token_generation=token_generation,
    )


def save_workbench_draft(
    db,
    *,
    session_uuid: str,
    user_id: int,
    raw_token: str,
    token_generation: int,
    payload: dict,
):
    return save_draft(
        db,
        session_uuid=session_uuid,
        user_id=user_id,
        raw_token=raw_token,
        token_generation=token_generation,
        payload=payload,
    )


def release_workbench(db, *, session_uuid: str, user_id: int, raw_token: str, token_generation: int, reason: str = "user_release"):
    return release(
        db,
        session_uuid=session_uuid,
        user_id=user_id,
        raw_token=raw_token,
        token_generation=token_generation,
        reason=reason,
    )


def expire_stale_sessions(db) -> int:
    return expire_stale(db)


def submit_workbench(db, *, session_uuid: str, user_id: int, raw_token: str, token_generation: int, payload: dict):
    return submit(
        db,
        session_uuid=session_uuid,
        user_id=user_id,
        raw_token=raw_token,
        token_generation=token_generation,
        payload=payload,
    )
