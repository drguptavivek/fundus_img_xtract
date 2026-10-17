"""remote_ai stage: remote AI inference runs and their per-image / per-target results."""
from __future__ import annotations

from sqlalchemy import select

from models import AIInferenceRun, AIModel, EncounterSetImage
from remote_inference.models import (
    EncounterAIImageResult,
    EncounterAIInferenceRun,
    EncounterAIOutputTarget,
    EncounterAITargetResult,
)

from .tables import BuildContext, _chunks, _json, drop_keys, redact_files

# Patient / file identifiers inside request payloads; kept only with an identifiers grant.
_IDENTIFYING = frozenset({"patient_id", "filename", "original_filename"})


def _scrub(value, pii: bool):
    """JSON payload from/to the provider; identifying keys (patient id, file names) only with an identifiers grant."""
    return value if pii or value is None else drop_keys(value, _IDENTIFYING)


def _task_runs(ctx: BuildContext) -> list[dict]:
    models = {m.id: m for m in ctx.db.execute(select(AIModel)).scalars()}
    task_info = {b.task.id: b for b in ctx.bundles}
    rows = []
    for chunk in _chunks(list(task_info)):
        for run in ctx.db.execute(select(AIInferenceRun).where(AIInferenceRun.task_id.in_(chunk)).order_by(AIInferenceRun.id)).scalars():
            bundle = task_info[run.task_id]
            model = models.get(run.ai_model_id)
            pii = ctx.allows_pii(bundle.encounter_id)
            rows.append({
                "run_scope": "task", "run_id": str(run.id),
                "encounter_uuid": ctx.encounter_uuid.get(bundle.encounter_id),
                "task_uuid": bundle.task.uuid, "image_uuid": bundle.image_uuid,
                "ai_model": model.name if model else None, "ai_model_version": model.version if model else None,
                "source": run.source, "status": run.status,
                "request_id": run.external_request_id, "prediction_id": run.prediction_id, "report_id": None,
                "http_status": run.http_status, "error_code": run.error_code, "error_message": redact_files(run.error_message, pii),
                "retry_count": run.retry_count,
                "created_at": run.created_at, "started_at": run.started_at, "finished_at": run.finished_at,
                "request_manifest": _json(_scrub(run.request_manifest_json, pii)),
                "response": _json(_scrub(run.execute_response_json, pii)),
                "config_snapshot": None,
            })
    return rows


def _encounter_runs(ctx: BuildContext) -> tuple[list[dict], dict]:
    models = {m.id: m for m in ctx.db.execute(select(AIModel)).scalars()}
    rows, runs = [], {}
    for chunk in _chunks(list(ctx.encounter_by_id)):
        for run in ctx.db.execute(
            select(EncounterAIInferenceRun).where(EncounterAIInferenceRun.patient_encounter_id.in_(chunk))
            .order_by(EncounterAIInferenceRun.id)
        ).scalars():
            model = models.get(run.ai_model_id)
            pii = ctx.allows_pii(run.patient_encounter_id)
            runs[run.id] = run
            rows.append({
                "run_scope": "encounter", "run_id": run.uuid,
                "encounter_uuid": ctx.encounter_uuid[run.patient_encounter_id],
                "task_uuid": None, "image_uuid": None,
                "ai_model": model.name if model else None, "ai_model_version": model.version if model else None,
                "source": run.source, "status": run.status,
                "request_id": run.request_id, "prediction_id": None, "report_id": run.report_id,
                "http_status": run.http_status, "error_code": run.error_code, "error_message": redact_files(run.error_message, pii),
                "retry_count": None,
                "created_at": run.created_at, "started_at": run.started_at, "finished_at": run.finished_at,
                "request_manifest": _json(_scrub(run.request_manifest_json, pii)),
                "response": _json(_scrub(run.submit_response_json, pii)),
                "config_snapshot": _json(_scrub(run.config_snapshot_json, pii)),
            })
    return rows, runs


def _image_and_target_rows(ctx: BuildContext, runs: dict) -> tuple[list[dict], list[dict]]:
    image_rows, target_rows = [], []
    results = []
    for chunk in _chunks(list(runs)):
        results.extend(ctx.db.execute(
            select(EncounterAIImageResult).where(EncounterAIImageResult.run_id.in_(chunk)).order_by(EncounterAIImageResult.id)
        ).scalars())
    image_ids = [r.encounter_set_image_id for r in results if r.encounter_set_image_id]
    uuid_by_image = {}
    for chunk in _chunks(image_ids):
        uuid_by_image.update(ctx.db.execute(
            select(EncounterSetImage.id, EncounterSetImage.uuid).where(EncounterSetImage.id.in_(chunk))
        ).all())
    for result in results:
        run = runs[result.run_id]
        image_rows.append({
            "run_id": run.uuid, "encounter_uuid": ctx.encounter_uuid[run.patient_encounter_id],
            "image_uuid": uuid_by_image.get(result.encounter_set_image_id),
            "remote_key": result.remote_key, "submitted_eye": result.submitted_eye, "detected_eye": result.detected_eye,
            "laterality_mismatch": result.laterality_mismatch, "is_primary": result.is_primary,
            "similarity_score": result.similarity_score, "upload_attempts": result.upload_attempts,
            "quality_state": result.quality_state, "raw_output": _json(_scrub(result.raw_output_json, ctx.allows_pii(run.patient_encounter_id))),
        })
    target_keys = dict(ctx.db.execute(select(EncounterAIOutputTarget.id, EncounterAIOutputTarget.target_key)).all())
    by_result = {r.id: r for r in results}
    for chunk in _chunks(list(by_result)):
        for target in ctx.db.execute(
            select(EncounterAITargetResult).where(EncounterAITargetResult.image_result_id.in_(chunk))
            .order_by(EncounterAITargetResult.id)
        ).scalars():
            result = by_result[target.image_result_id]
            run = runs[result.run_id]
            target_rows.append({
                "run_id": run.uuid, "encounter_uuid": ctx.encounter_uuid[run.patient_encounter_id],
                "image_uuid": uuid_by_image.get(result.encounter_set_image_id),
                "target_key": target_keys.get(target.output_target_id), "raw_label": target.raw_label,
                "raw_score": target.raw_score, "mapped_grade": target.mapped_grade,
                "derivation_reason": target.derivation_reason, "grade_id": target.grade_id,
            })
    return image_rows, target_rows


def build(ctx: BuildContext) -> dict[str, list[dict]]:
    encounter_run_rows, runs = _encounter_runs(ctx)
    image_rows, target_rows = _image_and_target_rows(ctx, runs)
    return {
        "ai_runs": _task_runs(ctx) + encounter_run_rows,
        "ai_image_results": image_rows,
        "ai_target_results": target_rows,
    }
