"""grading_timing stage: workbench sessions and per-task holds, for estimating time spent grading.

Excluded on purpose: session tokens, queue requests, configuration snapshots and draft observations.
"""
from __future__ import annotations

from sqlalchemy import select

from grading.workbench.models import GradingWorkbenchSession, GradingWorkbenchSessionTarget
from models import User

from .tables import BuildContext, _chunks


def _seconds(start, end):
    return (end - start).total_seconds() if start and end else None


def build(ctx: BuildContext) -> dict[str, list[dict]]:
    task_uuid = {bundle.task.id: bundle.task.uuid for bundle in ctx.bundles}
    usernames = dict(ctx.db.execute(select(User.id, User.username)).all())
    targets = []
    for chunk in _chunks(list(task_uuid)):
        targets.extend(ctx.db.execute(
            select(GradingWorkbenchSessionTarget).where(GradingWorkbenchSessionTarget.task_id.in_(chunk))
            .order_by(GradingWorkbenchSessionTarget.id)
        ).scalars())
    sessions = {}
    for chunk in _chunks(sorted({target.session_id for target in targets})):
        for session in ctx.db.execute(
            select(GradingWorkbenchSession).where(GradingWorkbenchSession.id.in_(chunk))
        ).scalars():
            sessions[session.id] = session
    session_rows = [
        {
            "session_uuid": session.uuid, "grader_username": usernames.get(session.user_id),
            "role_slot": session.role_slot, "workflow": session.workflow, "status": session.status,
            "root_task_uuid": task_uuid.get(session.root_task_id), "acquired_at": session.acquired_at,
            "last_heartbeat_at": session.last_heartbeat_at, "completed_at": session.completed_at,
            "released_at": session.released_at, "invalidated_at": session.invalidated_at,
            "close_reason": session.close_reason,
            "wall_seconds": _seconds(session.acquired_at, session.completed_at),
        }
        for session in sorted(sessions.values(), key=lambda s: s.id)
    ]
    target_rows = [
        {
            "session_uuid": sessions[target.session_id].uuid, "task_uuid": task_uuid[target.task_id],
            "role_slot": target.role_slot, "target_order": target.target_order,
            "target_purpose": target.target_purpose, "acquired_task_state": target.acquired_task_state,
            "acquired_at": target.acquired_at, "released_at": target.released_at,
            "release_reason": target.release_reason, "hold_seconds": _seconds(target.acquired_at, target.released_at),
            "submitted": target.release_reason == "submitted",
        }
        for target in targets
    ]
    return {"grading_sessions": session_rows, "grading_session_targets": target_rows}
