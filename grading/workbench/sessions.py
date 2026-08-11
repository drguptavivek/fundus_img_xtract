"""Durable workbench session lifecycle and token handling."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import timedelta

from sqlalchemy.orm import selectinload

from auth.utils import utcnow
from models import GradingTask
from utils.dualGradingEligibility import get_user_eligibility_for_task

from .builder import build_workbench
from .configuration import configuration_snapshot
from .errors import (
    ConfigurationChanged,
    SessionExpired,
    SessionSuperseded,
    SessionTokenInvalid,
    WorkbenchAccessDenied,
    WorkbenchNotFound,
)
from .models import GradingWorkbenchSession, GradingWorkbenchSessionTarget
from .package_workflow import editable_tasks


IDLE_MINUTES = 30
ABSOLUTE_MINUTES = 30


def issue_token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(32)
    return raw, _token_hash(raw)


def list_active(db, *, user_id: int) -> list[dict[str, object]]:
    expire_stale(db)
    rows = (
        db.query(GradingWorkbenchSession)
        .filter(GradingWorkbenchSession.user_id == user_id, GradingWorkbenchSession.status == "active")
        .order_by(GradingWorkbenchSession.acquired_at.desc())
        .all()
    )
    return [
        {
            "session_uuid": row.uuid,
            "role_slot": row.role_slot,
            "workflow": row.workflow,
            "acquired_at": row.acquired_at.isoformat(),
            "idle_expires_at": row.idle_expires_at.isoformat(),
            "absolute_expires_at": row.absolute_expires_at.isoformat(),
            "target_count": len(row.targets),
            "can_resume": True,
        }
        for row in rows
    ]


def load(db, *, session_uuid: str, user_id: int, raw_token: str, token_generation: int):
    session = _session_query(db, session_uuid, for_update=False)
    _authorize(session, user_id=user_id)
    _verify_active(session)
    _verify_token(session, raw_token=raw_token, token_generation=token_generation)
    tasks = _tasks_for_session(db, session)
    _assert_access(db, session=session, tasks=tasks, user_id=user_id)
    _assert_configuration(db, session=session, tasks=tasks)
    db.flush()
    return build_workbench(db, session, tasks)


def resume(db, *, session_uuid: str, user_id: int):
    session = _session_query(db, session_uuid, for_update=True)
    _authorize(session, user_id=user_id)
    _verify_active(session)
    tasks = _tasks_for_session(db, session, for_update=True)
    _assert_access(db, session=session, tasks=tasks, user_id=user_id)
    _assert_configuration(db, session=session, tasks=tasks)
    raw_token, token_hash = issue_token()
    session.token_hash = token_hash
    session.token_generation += 1
    now = utcnow()
    session.last_heartbeat_at = now
    session.idle_expires_at = min(now + timedelta(minutes=IDLE_MINUTES), session.absolute_expires_at)
    db.flush()
    return build_workbench(db, session, tasks), raw_token


def heartbeat(db, *, session_uuid: str, user_id: int, raw_token: str, token_generation: int):
    session = _session_query(db, session_uuid, for_update=True)
    _authorize(session, user_id=user_id)
    _verify_active(session)
    _verify_token(session, raw_token=raw_token, token_generation=token_generation)
    now = utcnow()
    session.last_heartbeat_at = now
    session.idle_expires_at = min(now + timedelta(minutes=IDLE_MINUTES), session.absolute_expires_at)
    db.flush()
    return {
        "session_uuid": session.uuid,
        "idle_expires_at": session.idle_expires_at.isoformat(),
        "absolute_expires_at": session.absolute_expires_at.isoformat(),
    }


def release(db, *, session_uuid: str, user_id: int, raw_token: str, token_generation: int, reason: str = "user_release"):
    session = _session_query(db, session_uuid, for_update=True)
    _authorize(session, user_id=user_id)
    if session.status != "active":
        return
    _verify_token(session, raw_token=raw_token, token_generation=token_generation)
    _close(session, status="released", reason=reason)
    db.flush()


def expire_stale(db) -> int:
    now = utcnow()
    rows = (
        db.query(GradingWorkbenchSession)
        .options(selectinload(GradingWorkbenchSession.targets))
        .filter(
            GradingWorkbenchSession.status == "active",
            (GradingWorkbenchSession.idle_expires_at <= now)
            | (GradingWorkbenchSession.absolute_expires_at <= now),
        )
        .with_for_update(skip_locked=True)
        .all()
    )
    for session in rows:
        reason = "absolute_expiry" if session.absolute_expires_at <= now else "idle_expiry"
        _close(session, status="expired", reason=reason, now=now)
    from .recovery import recover_incomplete_package_stages

    recovery = recover_incomplete_package_stages(db, now=now)
    if rows:
        db.flush()
    return len(rows) + recovery.expired_session_count


def new_session_times():
    now = utcnow()
    absolute = now + timedelta(minutes=ABSOLUTE_MINUTES)
    return now, now + timedelta(minutes=IDLE_MINUTES), absolute


def _session_query(db, session_uuid: str, *, for_update: bool):
    query = (
        db.query(GradingWorkbenchSession)
        .options(selectinload(GradingWorkbenchSession.targets))
        .filter(GradingWorkbenchSession.uuid == session_uuid)
    )
    if for_update:
        query = query.with_for_update()
    session = query.first()
    if session is None:
        raise WorkbenchNotFound("Grading workbench session not found.")
    return session


def _tasks_for_session(db, session, *, for_update: bool = False) -> list[GradingTask]:
    ordered_ids = [row.task_id for row in sorted(session.targets, key=lambda item: item.target_order)]
    query = db.query(GradingTask).filter(GradingTask.id.in_(ordered_ids))
    if for_update:
        query = query.order_by(GradingTask.id).with_for_update()
    tasks = {item.id: item for item in query.all()}
    if len(tasks) != len(ordered_ids):
        raise ConfigurationChanged("A leased grading target no longer exists.")
    return [tasks[item] for item in ordered_ids]


def _authorize(session, *, user_id: int) -> None:
    if session.user_id != user_id:
        raise WorkbenchAccessDenied("This grading session belongs to another user.")


def _verify_active(session) -> None:
    now = utcnow()
    if session.status != "active":
        if session.status == "invalidated":
            raise SessionSuperseded("This grading session was superseded.")
        raise SessionExpired("This grading session is no longer active.")
    if session.idle_expires_at <= now or session.absolute_expires_at <= now:
        _close(session, status="expired", reason="request_expiry", now=now)
        raise SessionExpired("This grading session expired. Acquire the task again.")


def _verify_token(session, *, raw_token: str, token_generation: int) -> None:
    if token_generation != session.token_generation:
        raise SessionSuperseded("A newer tab resumed this grading session.")
    if not raw_token or not hmac.compare_digest(session.token_hash, _token_hash(raw_token)):
        raise SessionTokenInvalid("The grading session token is invalid.")


def _assert_configuration(db, *, session, tasks) -> None:
    _snapshot, fingerprint = configuration_snapshot(
        db, tasks=tasks, workflow=session.workflow, role_slot=session.role_slot
    )
    if fingerprint != session.configuration_fingerprint:
        _close(session, status="invalidated", reason="configuration_changed")
        raise ConfigurationChanged("Grading configuration changed. Reload and acquire the work again.")


def _assert_access(db, *, session, tasks, user_id: int) -> None:
    if session.workflow == "package":
        package = tasks[0].encounter_set_package
        current_ids = {
            task.id for task in editable_tasks(package, session.role_slot, user_id)
        }
        leased_ids = {item.task_id for item in session.targets}
        if current_ids != leased_ids:
            _close(session, status="invalidated", reason="package_allocation_changed")
            raise WorkbenchAccessDenied(
                "The EncounterSet package allocation changed. Acquire it again."
            )
        # Sessions acquired before revision-window package targets were marked
        # editable can be repaired safely because the leased target set still
        # exactly matches the package's authoritative editable target set.
        for item in session.targets:
            item.target_purpose = "editable"
    elif session.workflow == "revision":
        for item in session.targets:
            item.target_purpose = "editable"

    editable_ids = {
        item.task_id for item in session.targets if item.target_purpose == "editable"
    }
    for task in tasks:
        if task.id in editable_ids and not get_user_eligibility_for_task(
            db, user_id, task.id, session.role_slot
        ):
            _close(session, status="invalidated", reason="allocation_changed")
            raise WorkbenchAccessDenied(
                "Your grading allocation changed. Acquire another workbench."
            )


def _close(session, *, status: str, reason: str, now=None) -> None:
    now = now or utcnow()
    session.status = status
    session.close_reason = reason
    if status == "completed":
        session.completed_at = now
    elif status == "invalidated":
        session.invalidated_at = now
    else:
        session.released_at = now
    for target in session.targets:
        if target.released_at is None:
            target.released_at = now
            target.release_reason = reason


def _token_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
