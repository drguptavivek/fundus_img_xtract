"""tasks and grades stages: grading tasks, every grade submission (human and AI) and the final decisions."""
from __future__ import annotations

import json

from sqlalchemy import select

from models import Disease, EncounterSetGradingScope

from .tables import BuildContext, _chunks, _json


def _features(raw):
    if not raw:
        return None
    try:
        return _json(json.loads(raw))
    except (TypeError, ValueError):
        return _json(raw)


def _scopes(ctx: BuildContext) -> dict:
    ids = sorted({b.task.encounter_set_scope_id for b in ctx.bundles if b.task.encounter_set_scope_id})
    found = {}
    for chunk in _chunks(ids):
        for scope in ctx.db.execute(select(EncounterSetGradingScope).where(EncounterSetGradingScope.id.in_(chunk))).scalars():
            found[scope.id] = scope
    return found


def build(ctx: BuildContext) -> dict[str, list[dict]]:
    scopes = _scopes(ctx)
    diseases = dict(ctx.db.execute(select(Disease.id, Disease.name)).all())
    tasks, grades, consensus = [], [], []
    for bundle in ctx.bundles:
        task = bundle.task
        encounter_uuid = ctx.encounter_uuid.get(bundle.encounter_id)
        disease = task.disease.name if task.disease else None
        package = task.encounter_set_package
        scope = scopes.get(task.encounter_set_scope_id)
        tasks.append({
            "task_uuid": task.uuid, "encounter_uuid": encounter_uuid, "image_uuid": bundle.image_uuid,
            "target_level": task.grading_target_level, "disease": disease, "task_source": task.task_source,
            "is_negative_control": bool(task.task_source and task.task_source.endswith("_negative_control")),
            "state": task.state, "lab_unit_id": task.lab_unit_id,
            "package_uuid": package.uuid if package else None, "package_code": package.code if package else None,
            "scope_uuid": scope.uuid if scope else None,
            "scope_disease": diseases.get(scope.scope_disease_id) if scope else None,
            "grade_count": len(bundle.grades), "created_at": task.created_at, "updated_at": task.updated_at,
        })
        for grade in bundle.grades:
            stats = getattr(grade, "_sync_annotation_stats", None)
            grades.append({
                "grade_id": grade.id, "task_uuid": task.uuid, "encounter_uuid": encounter_uuid,
                "image_uuid": bundle.image_uuid, "disease": disease, "role_slot": grade.role_slot,
                "grade_name": grade.grade_name, "grade_description": grade.grade_description,
                "grader_user_id": grade.grader_user_id,
                "grader_username": grade.grader.username if grade.grader else None,
                "comment": grade.comment, "selected_features": _features(grade.selected_features_json),
                "feature_geometry": _json(grade.feature_geometry_json),
                "annotation_count": stats[0] if stats else None,
                "time_taken_seconds": grade.time_taken, "started_at": grade.start_time,
                "ai_model": grade.ai_model_name, "ai_model_version": grade.ai_model_version,
                "ai_review_status": grade.ai_review_status, "ai_review_comment": grade.ai_review_comment,
                "ai_reviewed_by_user_id": grade.ai_reviewed_by_user_id, "ai_reviewed_at": grade.ai_reviewed_at,
                "created_at": grade.created_at, "updated_at": grade.updated_at,
            })
        decision = bundle.consensus
        if decision is not None:
            consensus.append({
                "task_uuid": task.uuid, "encounter_uuid": encounter_uuid, "image_uuid": bundle.image_uuid,
                "final_grade": decision.final_grade_name, "final_grade_description": decision.final_grade_description,
                "final_disease": decision.final_disease_name, "method": decision.method,
                "scope": decision.consensus_scope, "decided_by_user_id": decision.decided_by_user_id,
                "decided_at": decision.decided_at,
            })
    return {"tasks": tasks, "grades": grades, "consensus": consensus}
