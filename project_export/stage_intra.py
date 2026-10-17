"""intra_rater stage: repeat-grading batches, tasks and grades for tasks that are in the export."""
from __future__ import annotations

import json

from sqlalchemy import select

from models import (
    DirectImageUpload,
    Disease,
    DiseaseGrading,
    EncounterFile,
    IntraRaterBatch,
    IntraRaterGrade,
    IntraRaterTask,
    User,
)

from .tables import BuildContext, _chunks, _json


def _features(raw):
    if not raw:
        return None
    try:
        return _json(json.loads(raw))
    except (TypeError, ValueError):
        return _json(raw)


def build(ctx: BuildContext) -> dict[str, list[dict]]:
    task_uuid = {bundle.task.id: bundle.task.uuid for bundle in ctx.bundles}
    usernames = dict(ctx.db.execute(select(User.id, User.username)).all())
    diseases = dict(ctx.db.execute(select(Disease.id, Disease.name)).all())
    tasks = []
    for chunk in _chunks(list(task_uuid)):
        tasks.extend(ctx.db.execute(
            select(IntraRaterTask).where(IntraRaterTask.source_task_id.in_(chunk)).order_by(IntraRaterTask.id)
        ).scalars())
    file_ids = [t.encounter_file_id for t in tasks if t.encounter_file_id]
    direct_ids = [t.direct_image_upload_id for t in tasks if t.direct_image_upload_id]
    image_uuid = {}
    for chunk in _chunks(file_ids):
        image_uuid.update({("file", i): u for i, u in ctx.db.execute(
            select(EncounterFile.id, EncounterFile.uuid).where(EncounterFile.id.in_(chunk))).all()})
    for chunk in _chunks(direct_ids):
        image_uuid.update({("direct", i): u for i, u in ctx.db.execute(
            select(DirectImageUpload.id, DirectImageUpload.uuid).where(DirectImageUpload.id.in_(chunk))).all()})
    task_rows = [
        {
            "intra_task_uuid": t.uuid, "batch_id": t.batch_id, "source_task_uuid": task_uuid[t.source_task_id],
            "image_uuid": image_uuid.get(("file", t.encounter_file_id)) or image_uuid.get(("direct", t.direct_image_upload_id)),
            "grader_user_id": t.grader_user_id, "grader_username": usernames.get(t.grader_user_id),
            "disease": diseases.get(t.disease_id), "lab_unit_id": t.lab_unit_id, "state": t.state,
            "created_at": t.created_at, "updated_at": t.updated_at,
        }
        for t in tasks
    ]
    by_id = {t.id: t for t in tasks}
    grade_rows = []
    for chunk in _chunks(list(by_id)):
        for g in ctx.db.execute(
            select(IntraRaterGrade).where(IntraRaterGrade.task_id.in_(chunk)).order_by(IntraRaterGrade.id)
        ).scalars():
            grade_rows.append({
                "intra_grade_id": g.id, "intra_task_uuid": by_id[g.task_id].uuid, "batch_id": g.batch_id,
                "grader_user_id": g.grader_user_id, "grader_username": usernames.get(g.grader_user_id),
                "disease": g.disease_name or diseases.get(by_id[g.task_id].disease_id), "grade_name": g.grade_name,
                "grade_description": g.grade_description, "comment": g.comment,
                "selected_features": _features(g.selected_features_json),
                "feature_geometry": _json(g.feature_geometry_json), "time_taken_seconds": g.time_taken,
                "started_at": g.start_time, "created_at": g.created_at, "updated_at": g.updated_at,
            })
    labels = {}
    batch_rows = []
    for chunk in _chunks(sorted({t.batch_id for t in tasks})):
        for b in ctx.db.execute(select(IntraRaterBatch).where(IntraRaterBatch.id.in_(chunk)).order_by(IntraRaterBatch.id)).scalars():
            if b.normal_grade_id and b.normal_grade_id not in labels:
                labels[b.normal_grade_id] = ctx.db.get(DiseaseGrading, b.normal_grade_id)
            normal = labels.get(b.normal_grade_id)
            try:
                snapshot = json.loads(b.selection_snapshot_json) if b.selection_snapshot_json else None
            except ValueError:
                snapshot = b.selection_snapshot_json
            batch_rows.append({
                "batch_id": b.id, "disease": diseases.get(b.disease_id), "lab_unit_id": b.lab_unit_id,
                "created_by_username": usernames.get(b.created_by_user_id),
                "cooldown_days_override": b.cooldown_days_override, "target_images_per_grader": b.target_images_per_grader,
                "normal_grade": normal.impression if normal else None, "selection_snapshot": _json(snapshot),
                "remarks": b.remarks, "created_at": b.created_at, "updated_at": b.updated_at,
            })
    return {"intra_rater_batches": batch_rows, "intra_rater_tasks": task_rows, "intra_rater_grades": grade_rows}
