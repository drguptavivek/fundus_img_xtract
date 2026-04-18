from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4
import mimetypes
import re

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from auth.utils import utcnow
from db_transaction_manager import get_db_session, transaction_scope
from models import (
    AIInferenceRun,
    AIModelIntegration,
    DiseaseGrading,
    DirectImageUpload,
    EncounterFile,
    Grade,
    GradingTask,
    IMAGE_DIR,
    LabUnit,
    PatientEncounters,
    User,
    ZipFile,
)
from utils.fileUtils import abs_from_parts
from services.wadhwani_glaucoma_client import (
    WadhwaniClientError,
    execute_prediction,
    initialize_prediction,
    upload_prediction_file,
)


WADHWANI_PROVIDER = "wadhwani_glaucoma"
AI_PROBABILITY_PATTERN = re.compile(r"AI probability:\s*([0-9.]+)")


@dataclass
class WadhwaniInferenceResult:
    task_id: int
    ai_model_id: int
    inference_run_id: int | None
    grade_id: int | None
    status: str
    message: str
    reused_existing_grade: bool
    prediction_id: str | None
    confidence: float | None
    predicted_class: int | None
    predicted_class_name: str | None
    grade_impression: str | None
    error_code: str | None = None


class WadhwaniInferenceError(RuntimeError):
    def __init__(self, error_code: str, message: str):
        super().__init__(message)
        self.error_code = error_code
        self.message = message


def run_task_batch(
    task_ids: list[int],
    *,
    requested_by_user_id: int | None,
    force: bool = False,
    stop_on_error: bool = False,
) -> list[WadhwaniInferenceResult]:
    results: list[WadhwaniInferenceResult] = []
    for task_id in task_ids:
        result = run_task_inference(task_id=task_id, requested_by_user_id=requested_by_user_id, force=force)
        results.append(result)
        if stop_on_error and result.status == "failed":
            break
    return results


def run_task_inference(
    *,
    task_id: int,
    requested_by_user_id: int | None,
    force: bool = False,
) -> WadhwaniInferenceResult:
    try:
        with get_db_session() as db:
            integration = _get_linked_integration(db)
            ai_model_id = integration.ai_model_id
            integration_id = integration.id
            client_id = integration.client_id
            bearer_token = integration.bearer_token
            task = _load_task(db, task_id)
            existing_grade = _get_existing_ai_grade(db, task.id, ai_model_id)
            if existing_grade is not None:
                return _result_from_grade(task.id, ai_model_id, existing_grade, "Existing AI grade already present for linked Wadhwani model.")

            cached_run = _get_latest_successful_run(db, task.id, ai_model_id)
            if cached_run is not None and cached_run.execute_response_json:
                ai_system = _get_ai_system_user(db)
                grade = _restore_grade_from_cached_run(
                    db,
                    task=task,
                    integration=integration,
                    ai_system=ai_system,
                    execute_payload=cached_run.execute_response_json,
                )
                db.flush()
                return WadhwaniInferenceResult(
                    task_id=task.id,
                    ai_model_id=ai_model_id,
                    inference_run_id=None,
                    grade_id=grade.id,
                    status="success",
                    message="Reused cached successful inference.",
                    reused_existing_grade=True,
                    prediction_id=cached_run.prediction_id,
                    confidence=_extract_probability(cached_run.execute_response_json),
                    predicted_class=_extract_result_row(cached_run.execute_response_json).get("predicted_class"),
                    predicted_class_name=_extract_result_row(cached_run.execute_response_json).get("predicted_class_name"),
                    grade_impression=grade.grade_name,
                )
    except WadhwaniInferenceError as exc:
        return WadhwaniInferenceResult(
            task_id=task_id,
            ai_model_id=0,
            inference_run_id=None,
            grade_id=None,
            status="failed",
            message=exc.message,
            reused_existing_grade=False,
            prediction_id=None,
            confidence=None,
            predicted_class=None,
            predicted_class_name=None,
            grade_impression=None,
            error_code=exc.error_code,
        )

    image_ref = _resolve_task_image_reference(task_id)
    request_id = _build_request_id(task_id, ai_model_id)
    run_id = _create_inference_run(
        task_id=task_id,
        ai_model_id=ai_model_id,
        integration_id=integration_id,
        requested_by_user_id=requested_by_user_id,
        request_id=request_id,
        image_ref=image_ref,
    )

    try:
        initialize_payload = initialize_prediction(
            client_id=client_id,
            bearer_token=bearer_token,
            request_id=request_id,
            filename=image_ref["filename"],
            content_type=image_ref["content_type"],
        )
        prediction_id = initialize_payload.get("prediction_id")
        upload_url = ((initialize_payload.get("results") or [{}])[0]).get("upload_url")
        if not prediction_id or not upload_url:
            raise WadhwaniInferenceError("invalid_response", "Initialize response missing prediction_id or upload_url")

        upload_prediction_file(
            upload_url=upload_url,
            content_type=image_ref["content_type"],
            image_bytes=image_ref["image_bytes"],
        )
        execute_payload = execute_prediction(
            client_id=client_id,
            bearer_token=bearer_token,
            prediction_id=prediction_id,
            external_request_id=request_id,
            manifest=[image_ref["manifest"]],
        )

        with transaction_scope() as db:
            task = _load_task(db, task_id)
            integration = _get_linked_integration(db)
            ai_system = _get_ai_system_user(db)
            grade = _restore_grade_from_cached_run(
                db,
                task=task,
                integration=integration,
                ai_system=ai_system,
                execute_payload=execute_payload,
            )
            run = db.get(AIInferenceRun, run_id)
            if run is None:
                raise WadhwaniInferenceError("invalid_response", "Inference run record missing")
            run.status = "success"
            run.prediction_id = prediction_id
            run.http_status = 200
            run.request_manifest_json = image_ref["manifest"]
            run.initialize_response_json = initialize_payload
            run.execute_response_json = execute_payload
            run.finished_at = utcnow()
            db.flush()

            result_row = _extract_result_row(execute_payload)
            return WadhwaniInferenceResult(
                task_id=task.id,
                ai_model_id=ai_model_id,
                inference_run_id=run.id,
                grade_id=grade.id,
                status="success",
                message="Inference completed successfully.",
                reused_existing_grade=False,
                prediction_id=prediction_id,
                confidence=_extract_probability(execute_payload),
                predicted_class=result_row.get("predicted_class"),
                predicted_class_name=result_row.get("predicted_class_name"),
                grade_impression=grade.grade_name,
            )
    except WadhwaniClientError as exc:
        _mark_run_failed(run_id, exc.step + "_failed", exc.status_code, exc.payload, str(exc))
        return WadhwaniInferenceResult(
            task_id=task_id,
            ai_model_id=ai_model_id,
            inference_run_id=run_id,
            grade_id=None,
            status="failed",
            message=str(exc),
            reused_existing_grade=False,
            prediction_id=None,
            confidence=None,
            predicted_class=None,
            predicted_class_name=None,
            grade_impression=None,
            error_code=exc.step + "_failed",
        )
    except WadhwaniInferenceError as exc:
        _mark_run_failed(run_id, exc.error_code, None, None, exc.message)
        return WadhwaniInferenceResult(
            task_id=task_id,
            ai_model_id=ai_model_id,
            inference_run_id=run_id,
            grade_id=None,
            status="failed",
            message=exc.message,
            reused_existing_grade=False,
            prediction_id=None,
            confidence=None,
            predicted_class=None,
            predicted_class_name=None,
            grade_impression=None,
            error_code=exc.error_code,
        )


def _get_linked_integration(db) -> AIModelIntegration:
    integration = db.execute(
        select(AIModelIntegration)
        .options(selectinload(AIModelIntegration.ai_model))
        .where(AIModelIntegration.provider == WADHWANI_PROVIDER)
        .where(AIModelIntegration.is_enabled.is_(True))
        .order_by(AIModelIntegration.updated_at.desc(), AIModelIntegration.id.desc())
    ).scalars().first()
    if integration is None:
        raise WadhwaniInferenceError("integration_not_configured", "No linked Wadhwani integration is configured.")
    return integration


def _load_task(db, task_id: int) -> GradingTask:
    task = db.execute(
        select(GradingTask)
        .options(
            selectinload(GradingTask.disease),
            selectinload(GradingTask.lab_unit).selectinload(LabUnit.hospital),
            selectinload(GradingTask.encounter_file).selectinload(EncounterFile.camera),
            selectinload(GradingTask.encounter_file).selectinload(EncounterFile.patient_encounter).selectinload(PatientEncounters.zip_file),
            selectinload(GradingTask.direct_image).selectinload(DirectImageUpload.camera),
            selectinload(GradingTask.direct_image).selectinload(DirectImageUpload.hospital),
            selectinload(GradingTask.direct_image).selectinload(DirectImageUpload.lab_unit),
        )
        .where(GradingTask.id == task_id)
    ).scalar_one_or_none()
    if task is None:
        raise WadhwaniInferenceError("task_not_found", f"Task {task_id} was not found.")
    if not task.disease or task.disease.name != "Glaucoma":
        raise WadhwaniInferenceError("not_glaucoma_task", "Wadhwani inference supports only glaucoma tasks.")
    if task.patient_encounter_id and task.encounter_file_id is None and task.direct_image_upload_id is None:
        raise WadhwaniInferenceError(
            "encounter_set_task_not_supported",
            "Task is an encounter-set task and does not identify a single image to send to Wadhwani.",
        )
    if task.encounter_file_id is None and task.direct_image_upload_id is None:
        raise WadhwaniInferenceError("image_not_found", "Task does not reference a concrete image.")
    return task


def _get_ai_system_user(db) -> User:
    user = db.execute(select(User).where(User.username == "ai_system")).scalar_one_or_none()
    if user is None:
        user = User(
            username="ai_system",
            password_hash="not-used",
            is_active=False,
            full_name="AI System",
            designation="System",
        )
        db.add(user)
        db.flush()
    return user


def _get_existing_ai_grade(db, task_id: int, ai_model_id: int) -> Grade | None:
    return db.execute(
        select(Grade)
        .where(Grade.task_id == task_id)
        .where(Grade.role_slot == "ai")
        .where(Grade.ai_model_id == ai_model_id)
    ).scalar_one_or_none()


def _get_latest_successful_run(db, task_id: int, ai_model_id: int) -> AIInferenceRun | None:
    return db.execute(
        select(AIInferenceRun)
        .where(AIInferenceRun.task_id == task_id)
        .where(AIInferenceRun.ai_model_id == ai_model_id)
        .where(AIInferenceRun.status == "success")
        .order_by(AIInferenceRun.created_at.desc())
    ).scalars().first()


def _result_from_grade(task_id: int, ai_model_id: int, grade: Grade, message: str) -> WadhwaniInferenceResult:
    probability = None
    if grade.comment:
        match = AI_PROBABILITY_PATTERN.search(grade.comment)
        if match:
            probability = float(match.group(1))
    return WadhwaniInferenceResult(
        task_id=task_id,
        ai_model_id=ai_model_id,
        inference_run_id=None,
        grade_id=grade.id,
        status="skipped",
        message=message,
        reused_existing_grade=True,
        prediction_id=None,
        confidence=probability,
        predicted_class=None,
        predicted_class_name=None,
        grade_impression=grade.grade_name,
    )


def _resolve_task_image_reference(task_id: int) -> dict[str, Any]:
    with get_db_session() as db:
        task = _load_task(db, task_id)
        if task.direct_image is not None:
            return _resolve_direct_image(task)
        if task.encounter_file is not None:
            return _resolve_encounter_image(task)
    raise WadhwaniInferenceError("image_not_found", "Task does not reference a concrete image.")


def _resolve_direct_image(task: GradingTask) -> dict[str, Any]:
    direct = task.direct_image
    if direct is None:
        raise WadhwaniInferenceError("image_not_found", "Direct image is missing.")

    if direct.edited_filename:
        filename = direct.edited_filename
        kind = "edited"
        s3_key = direct.s3_object_key_edited
    else:
        filename = direct.filename
        kind = "orig"
        s3_key = direct.s3_object_key
    if not filename:
        raise WadhwaniInferenceError("image_not_found", "Direct image filename is missing.")

    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    image_bytes = _read_direct_image_bytes(direct, filename, kind, s3_key)

    manifest = {
        "filename": filename,
        "capture_date": direct.created_at.isoformat() if direct.created_at else None,
        "hospital_name": direct.hospital.name if direct.hospital else None,
        "lab_unit_name": direct.lab_unit.name if direct.lab_unit else None,
        "camera_type": direct.camera.name if direct.camera else None,
    }
    manifest = {key: value for key, value in manifest.items() if value is not None}
    return {
        "filename": filename,
        "content_type": content_type,
        "image_bytes": image_bytes,
        "manifest": manifest,
    }


def _resolve_encounter_image(task: GradingTask) -> dict[str, Any]:
    encounter_file = task.encounter_file
    if encounter_file is None or not encounter_file.filename:
        raise WadhwaniInferenceError("image_not_found", "Encounter image filename is missing.")
    patient_encounter = encounter_file.patient_encounter
    zip_file = patient_encounter.zip_file if patient_encounter else None
    if zip_file is None or zip_file.upload_date is None:
        raise WadhwaniInferenceError("image_not_found", "Encounter image upload date is missing.")

    content_type = mimetypes.guess_type(encounter_file.filename)[0] or "application/octet-stream"
    image_bytes = _read_encounter_image_bytes(encounter_file, zip_file.upload_date, encounter_file.s3_object_key)
    manifest = {
        "filename": encounter_file.filename,
        "laterality": _normalize_laterality(encounter_file.eye_side),
        "focus": _normalize_focus(encounter_file.centering),
        "capture_date": _capture_date_for_encounter(patient_encounter.capture_date_dt if patient_encounter else None),
        "hospital_name": task.lab_unit.hospital.name if task.lab_unit and task.lab_unit.hospital else None,
        "lab_unit_name": task.lab_unit.name if task.lab_unit else None,
        "camera_type": encounter_file.camera.name if encounter_file.camera else None,
    }
    manifest = {key: value for key, value in manifest.items() if value is not None}
    return {
        "filename": encounter_file.filename,
        "content_type": content_type,
        "image_bytes": image_bytes,
        "manifest": manifest,
    }


def _read_direct_image_bytes(direct: DirectImageUpload, filename: str, kind: str, s3_key: str | None) -> bytes:
    if direct.s3_config and s3_key:
        from utils.s3_prefix import apply_global_prefix
        from utils.s3_storage_backends import get_s3_client

        client = get_s3_client(direct.s3_config)
        response = client.get_object(
            Bucket=direct.s3_config.bucket_name,
            Key=apply_global_prefix(s3_key),
        )
        return response["Body"].read()
    path = abs_from_parts(direct.folder_rel, filename, kind)
    if not path.exists():
        raise WadhwaniInferenceError("image_not_found", f"Direct image file is missing: {path}")
    return path.read_bytes()


def _read_encounter_image_bytes(encounter_file: EncounterFile, upload_date, s3_key: str | None) -> bytes:
    if encounter_file.s3_config and s3_key:
        from utils.s3_prefix import apply_global_prefix
        from utils.s3_storage_backends import get_s3_client

        client = get_s3_client(encounter_file.s3_config)
        response = client.get_object(
            Bucket=encounter_file.s3_config.bucket_name,
            Key=apply_global_prefix(s3_key),
        )
        return response["Body"].read()
    path = IMAGE_DIR / upload_date.strftime("%Y_%m_%d") / encounter_file.filename
    if not path.exists():
        raise WadhwaniInferenceError("image_not_found", f"Encounter image file is missing: {path}")
    return path.read_bytes()


def _capture_date_for_encounter(capture_date) -> str | None:
    if capture_date is None:
        return None
    return datetime.combine(capture_date, datetime.min.time(), tzinfo=timezone.utc).isoformat()


def _normalize_laterality(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower()
    if normalized in {"l", "left"}:
        return "left"
    if normalized in {"r", "right"}:
        return "right"
    return None


def _normalize_focus(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower()
    if normalized in {"disk", "disc", "onh", "optic_disc", "optic nerve head"}:
        return "disc"
    return None


def _build_request_id(task_id: int, ai_model_id: int) -> str:
    return f"wdh-g-task-{task_id}-model-{ai_model_id}-{uuid4().hex[:12]}"


def _create_inference_run(
    *,
    task_id: int,
    ai_model_id: int,
    integration_id: int,
    requested_by_user_id: int | None,
    request_id: str,
    image_ref: dict[str, Any],
) -> int:
    with transaction_scope() as db:
        run = AIInferenceRun(
            task_id=task_id,
            ai_model_id=ai_model_id,
            integration_id=integration_id,
            requested_by_user_id=requested_by_user_id,
            source="internal",
            status="running",
            external_request_id=request_id,
            remote_filename=image_ref["filename"],
            remote_content_type=image_ref["content_type"],
            started_at=utcnow(),
        )
        db.add(run)
        db.flush()
        return run.id


def _mark_run_failed(run_id: int, error_code: str, http_status: int | None, payload: Any, message: str) -> None:
    with transaction_scope() as db:
        run = db.get(AIInferenceRun, run_id)
        if run is None:
            return
        run.status = "failed"
        run.error_code = error_code
        run.error_message = message
        run.http_status = http_status
        if error_code == "initialize_failed":
            run.initialize_response_json = payload if isinstance(payload, dict) else None
        elif error_code == "execute_failed":
            run.execute_response_json = payload if isinstance(payload, dict) else None
        run.finished_at = utcnow()


def _restore_grade_from_cached_run(db, *, task: GradingTask, integration: AIModelIntegration, ai_system: User, execute_payload: dict[str, Any]) -> Grade:
    result_row = _extract_result_row(execute_payload)
    grading = _map_result_to_grading(db, task.disease_id, result_row)
    probability = _extract_probability(execute_payload)
    comment = "\n".join(
        [
            f"AI probability: {probability:.4f}",
            f"Prediction ID: {execute_payload.get('prediction_id', '')}".strip(),
            f"Prediction: {result_row.get('prediction', '')}".strip(),
            f"Predicted class: {result_row.get('predicted_class', '')}".strip(),
            f"Predicted class name: {result_row.get('predicted_class_name', '')}".strip(),
            f"External request ID: {execute_payload.get('external_request_id', '')}".strip(),
        ]
    ).strip()
    existing = _get_existing_ai_grade(db, task.id, integration.ai_model_id)
    if existing is None:
        existing = Grade(
            task_id=task.id,
            grader_user_id=ai_system.id,
            role_slot="ai",
            disease_grading_id=grading.id,
            time_taken=0,
            start_time=utcnow(),
            ai_model_id=integration.ai_model_id,
        )
        db.add(existing)
    existing.grader_user_id = ai_system.id
    existing.disease_grading_id = grading.id
    existing.comment = comment
    existing.disease_name = grading.disease.name
    existing.grade_name = grading.impression
    existing.grade_description = grading.guidelines
    existing.ai_model_id = integration.ai_model_id
    existing.ai_model_name = integration.ai_model.name if integration.ai_model else None
    existing.ai_model_version = integration.ai_model.version if integration.ai_model else None
    db.flush()
    return existing


def _extract_result_row(execute_payload: dict[str, Any]) -> dict[str, Any]:
    results = execute_payload.get("results") or []
    if not results:
        raise WadhwaniInferenceError("invalid_response", "Execute response did not include any results.")
    return results[0]


def _extract_probability(execute_payload: dict[str, Any]) -> float:
    result_row = _extract_result_row(execute_payload)
    probability = result_row.get("model_score")
    if probability is None:
        probability = result_row.get("confidence")
    if probability is None:
        raise WadhwaniInferenceError("invalid_response", "Execute response did not include model_score or confidence.")
    return float(probability)


def _map_result_to_grading(db, disease_id: int, result_row: dict[str, Any]) -> DiseaseGrading:
    predicted_class_name = (result_row.get("predicted_class_name") or "").strip().lower()
    prediction = (result_row.get("prediction") or "").strip().lower()
    predicted_class = result_row.get("predicted_class")

    positive = (
        prediction == "referrable"
        or predicted_class == 1
        or "glaucoma" in predicted_class_name
    )
    impression = "Glaucoma" if positive else "Normal"
    grading = db.execute(
        select(DiseaseGrading)
        .where(DiseaseGrading.disease_id == disease_id)
        .where(DiseaseGrading.impression == impression)
    ).scalar_one_or_none()
    if grading is None:
        raise WadhwaniInferenceError("grading_mapping_missing", f"Could not find disease grading '{impression}'.")
    return grading
