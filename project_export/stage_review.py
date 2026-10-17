"""discrepancy_review stage: review submissions, regrade assignments and bulk review corrections."""
from __future__ import annotations

from sqlalchemy import select, text

from models import Disease, RegradeTask, User
from review_history.models import ReviewSubmissionHistory

from .tables import BuildContext, _chunks, _json


def build(ctx: BuildContext) -> dict[str, list[dict]]:
    task_uuid = {bundle.task.id: bundle.task.uuid for bundle in ctx.bundles}
    task_ids = list(task_uuid)
    usernames = dict(ctx.db.execute(select(User.id, User.username)).all())
    diseases = dict(ctx.db.execute(select(Disease.id, Disease.name)).all())
    history, regrades, corrections = [], [], []
    for chunk in _chunks(task_ids):
        for item in ctx.db.execute(
            select(ReviewSubmissionHistory).where(ReviewSubmissionHistory.task_id.in_(chunk))
            .order_by(ReviewSubmissionHistory.id)
        ).scalars():
            history.append({
                "request_id": item.request_id, "task_uuid": task_uuid[item.task_id],
                "actor_username": usernames.get(item.actor_user_id), "action_type": item.action_type,
                "source": item.source, "recorded_at": item.recorded_at,
                "before": _json(item.before_json), "after": _json(item.after_json), "note": item.note,
            })
        for item in ctx.db.execute(
            select(RegradeTask).where(RegradeTask.source_task_id.in_(chunk)).order_by(RegradeTask.id)
        ).scalars():
            regrades.append({
                "regrade_uuid": item.uuid, "source_task_uuid": task_uuid[item.source_task_id],
                "disease": diseases.get(item.disease_id), "lab_unit_id": item.lab_unit_id,
                "assigned_to_username": usernames.get(item.assigned_to_user_id),
                "created_by_username": usernames.get(item.created_by_user_id), "status": item.status,
                "notes": item.notes, "created_at": item.created_at, "updated_at": item.updated_at,
            })
        # No ORM model for the archive table (written by a one-off migration script), so plain SQL.
        for row in ctx.db.execute(
            text("SELECT original_grade_id, task_id, migration_id, script_name, archived_at, payload_json "
                 "FROM review_grade_correction_archive WHERE task_id = ANY(:ids) ORDER BY id"),
            {"ids": chunk},
        ).all():
            corrections.append({
                "original_grade_id": row[0], "task_uuid": task_uuid[row[1]], "migration_id": row[2],
                "script_name": row[3], "archived_at": row[4], "payload": _json(row[5]),
            })
    return {"review_history": history, "regrade_tasks": regrades, "review_corrections": corrections}
