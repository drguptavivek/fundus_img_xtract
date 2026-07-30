from __future__ import annotations

import json
import logging
import re
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

from flask import current_app, send_file
from sqlalchemy import select
from sqlalchemy.orm import object_session
from werkzeug.datastructures import FileStorage, MultiDict
from werkzeug.utils import secure_filename

from auth.utils import utcnow
from job_store import db_create_job
from models import (
    AIInferenceRun,
    AIModelIntegration,
    DIRECT_UPLOAD_DIR,
    UPLOAD_DIR,
    DirectImageUpload,
    EncounterSetImage,
    Grade,
    Job,
    JobItem,
    PatientEncounters,
    User,
)
from services.wadhwani_glaucoma_inference import WADHWANI_PROVIDER
from services.glaucoma_ai_upload import GLAUCOMA_AI_UPLOAD_VERIFICATION_REMARK
from services.encounter_referral_suggestion import normalize_referral_positive_diseases, normalize_referral_suggestion
from .direct import (
    DirectUploadActor,
    DirectUploadJobError,
    DirectUploadJobRequest,
    create_direct_upload_job,
    direct_upload_response_payload,
    enqueue_direct_upload_post_commit,
)
from upload_profiles.models import PatientEncounterTargetDisease
from upload_profiles.service import (
    UPLOAD_KIND_DIRECT_IMAGE,
    UPLOAD_KIND_ENCOUNTER_SET,
    UPLOAD_KIND_PREGRADED,
    UPLOAD_KIND_REMIDIO,
    UploadOptions,
    validate_profile_upload_scope,
    validate_remedio_upload_scope,
)
from utils.celery_helpers import enqueue_task
from utils.fileUtils import get_direct_thumbnail_serving_path
from utils.log_sanitize import sanitize_log_value


logger = logging.getLogger(__name__)
MOBILE_UPLOAD_KINDS = {UPLOAD_KIND_DIRECT_IMAGE, UPLOAD_KIND_REMIDIO, UPLOAD_KIND_ENCOUNTER_SET}
MAX_REMARKS_LENGTH = 1000
AI_PROBABILITY_PATTERN = re.compile(r"AI probability:\s*([0-9.]+)")
AI_PREDICTED_CLASS_NAME_PATTERN = re.compile(r"Predicted class name:\s*(.+)")


class MobileUploadError(ValueError):
    def __init__(self, message: str, *, code: str = "invalid_upload", status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True)
class _Actor:
    user_id: int
    username: str | None
    remote_addr: str | None


def serialize_mobile_upload_options(options: UploadOptions, *, db=None) -> dict[str, Any]:
    executable_model_ids = _executable_ai_model_ids(db) if db is not None else None
    profiles = []
    for profile in options.profiles:
        upload_kinds = [kind for kind in profile["upload_kinds"] if kind in MOBILE_UPLOAD_KINDS]
        if not upload_kinds:
            continue
        payload = dict(profile)
        payload["upload_kinds"] = upload_kinds
        payload["ai_workflows"] = [
            workflow
            for workflow in payload.get("ai_workflows", [])
            if workflow.get("upload_kind") in upload_kinds
            and (executable_model_ids is None or int(workflow.get("ai_model_id") or 0) in executable_model_ids)
        ]
        profiles.append(payload)
    return {
        "projects": _filter_options(options.projects, {profile["project_id"] for profile in profiles}),
        "lab_units": _filter_options(options.lab_units, {profile["lab_unit_id"] for profile in profiles}),
        "diseases": _filter_options(options.diseases, {disease_id for profile in profiles for disease_id in profile["disease_ids"]}),
        "cameras": _filter_options(options.cameras, {camera_id for profile in profiles for camera_id in profile["camera_ids"]}),
        "areas": _filter_options(options.areas, {area_id for profile in profiles for area_id in profile["area_ids"]}),
        "profiles": profiles,
    }


def create_mobile_upload(*, db, user_id: int, form: MultiDict, files: MultiDict, remote_addr: str | None = None) -> dict[str, Any]:
    actor = _actor(db, user_id, remote_addr)
    idempotency_key = _required_text(form, "idempotency_key")
    existing = _job_by_idempotency_key(db, user_id=user_id, idempotency_key=idempotency_key)
    if existing is not None:
        return _upload_response_from_job(existing)
    upload_kind = _required_text(form, "upload_kind")
    if upload_kind == UPLOAD_KIND_PREGRADED:
        raise MobileUploadError("Pregraded uploads are webapp-only.", code="unsupported_upload_kind")
    if upload_kind not in MOBILE_UPLOAD_KINDS:
        raise MobileUploadError("Unsupported upload kind.", code="unsupported_upload_kind")

    if upload_kind == UPLOAD_KIND_DIRECT_IMAGE:
        return _create_direct_upload(db=db, actor=actor, form=form, files=files, idempotency_key=idempotency_key)
    if upload_kind == UPLOAD_KIND_REMIDIO:
        return _create_remidio_upload(db=db, actor=actor, form=form, files=files, idempotency_key=idempotency_key)
    return _create_encounter_set_upload(db=db, actor=actor, form=form, files=files, idempotency_key=idempotency_key)


def get_mobile_upload_status(*, db, user_id: int, upload_token: str) -> dict[str, Any]:
    job = _scoped_job(db, user_id, upload_token)
    return _job_payload(job)


def get_mobile_upload_status_by_idempotency_key(*, db, user_id: int, idempotency_key: str) -> dict[str, Any]:
    job = _job_by_idempotency_key(db, user_id=user_id, idempotency_key=idempotency_key)
    if job is None:
        raise MobileUploadError("Upload was not found.", code="upload_not_found", status_code=404)
    return _job_payload(job)


def get_mobile_upload_inference(*, db, user_id: int, upload_token: str) -> dict[str, Any]:
    job = _scoped_job(db, user_id, upload_token)
    thumbnail_urls = _available_direct_thumbnail_urls(job)
    task_ids = [item.task_id for item in job.items if item.task_id]
    if not task_ids:
        return {
            "upload_token": job.token,
            "status": "not_configured",
            "items": [_inference_item_payload(item, thumbnail_urls, None) for item in job.items],
            "results": [],
        }
    runs = (
        db.execute(
            select(AIInferenceRun)
            .where(AIInferenceRun.task_id.in_(task_ids))
            .order_by(AIInferenceRun.created_at.desc(), AIInferenceRun.id.desc())
        )
        .scalars()
        .all()
    )
    latest_runs = _latest_inference_runs_by_task(runs)
    grade_results = _latest_ai_grade_results(db, task_ids)
    grades_by_task = {result["task_id"]: result for result in grade_results}
    item_results = [
        _inference_item_payload(
            item,
            thumbnail_urls,
            _inference_result_for_item(item, latest_runs, grades_by_task),
        )
        for item in job.items
    ]
    results = [item["inference"] for item in item_results if item.get("inference")]
    status = _aggregate_inference_status(item_results)
    return {
        "upload_token": job.token,
        "status": status,
        "items": item_results,
        "results": results,
    }


def retry_mobile_upload_inference(
    *,
    db,
    user_id: int,
    upload_token: str,
    requested_task_ids: list[int] | None = None,
) -> dict[str, Any]:
    job = _scoped_job(db, user_id, upload_token)
    task_ids = [item.task_id for item in job.items if item.task_id]
    if requested_task_ids:
        requested = set(requested_task_ids)
        task_ids = [task_id for task_id in task_ids if task_id in requested]
    if not task_ids:
        raise MobileUploadError("No inference-capable images were found for this upload.", code="inference_not_configured", status_code=400)

    latest_runs = _latest_inference_runs_by_task(
        db.execute(
            select(AIInferenceRun)
            .where(AIInferenceRun.task_id.in_(task_ids))
            .order_by(AIInferenceRun.created_at.desc(), AIInferenceRun.id.desc())
        )
        .scalars()
        .all()
    )
    retry_task_ids = [
        task_id
        for task_id in task_ids
        if latest_runs.get(task_id) is not None and latest_runs[task_id].status == "failed"
    ]
    if not retry_task_ids:
        raise MobileUploadError("No failed inference results were found to retry.", code="no_failed_inference", status_code=409)

    inference_job_token = db_create_job(
        [f"task:{task_id}" for task_id in retry_task_ids],
        [],
        uploader_user_id=user_id,
        uploader_username=job.uploader_username,
        uploader_ip=job.uploader_ip,
        lab_unit_id=job.lab_unit_id,
        project_id=job.project_id,
        upload_type="mobile_direct_image_inference_retry",
        upload_kind=job.upload_kind,
        upload_profile_id=job.upload_profile_id,
    )
    enqueue_task(
        "celery_tasks.tasks.wadhwani_tasks.run_wadhwani_glaucoma_batch_task",
        inference_job_token,
        retry_task_ids,
        user_id=user_id,
    )
    return {
        "upload_token": job.token,
        "retry_job_token": inference_job_token,
        "queued_task_ids": retry_task_ids,
        "queued_count": len(retry_task_ids),
    }


def _latest_inference_runs_by_task(runs: list[AIInferenceRun]) -> dict[int, AIInferenceRun]:
    latest: dict[int, AIInferenceRun] = {}
    for run in runs:
        latest.setdefault(run.task_id, run)
    return latest


def _latest_ai_grade_results(db, task_ids: list[int]) -> list[dict[str, Any]]:
    grades = (
        db.execute(
            select(Grade)
            .where(Grade.task_id.in_(task_ids))
            .where(Grade.role_slot == "ai")
            .order_by(Grade.updated_at.desc(), Grade.id.desc())
        )
        .scalars()
        .all()
    )
    seen: set[int] = set()
    results: list[dict[str, Any]] = []
    for grade in grades:
        if grade.task_id in seen:
            continue
        seen.add(grade.task_id)
        results.append(
            {
                "task_id": grade.task_id,
                "ai_model_id": grade.ai_model_id,
                "provider": WADHWANI_PROVIDER if grade.ai_model_id else None,
                "status": "success",
                "prediction_id": None,
                "prediction": None,
                "predicted_class_name": _predicted_class_name_from_grade_comment(grade.comment) or grade.grade_name,
                "confidence": _confidence_from_grade_comment(grade.comment),
                "error_code": None,
                "error_message": None,
                "updated_at": _iso(grade.updated_at),
            }
        )
    return results


def _inference_result_for_item(
    item: JobItem,
    latest_runs: dict[int, AIInferenceRun],
    grades_by_task: dict[int, dict[str, Any]],
) -> dict[str, Any] | None:
    if not item.task_id:
        return None
    grade_result = grades_by_task.get(item.task_id)
    if grade_result is not None:
        return grade_result
    run = latest_runs.get(item.task_id)
    if run is None:
        return {
            "task_id": item.task_id,
            "ai_model_id": None,
            "provider": None,
            "status": "pending",
            "prediction_id": None,
            "prediction": None,
            "predicted_class_name": None,
            "confidence": None,
            "error_code": None,
            "error_message": None,
            "updated_at": None,
        }
    return {
        "task_id": run.task_id,
        "ai_model_id": run.ai_model_id,
        "provider": run.integration.provider if run.integration else None,
        "status": run.status,
        "prediction_id": run.prediction_id,
        "execute_response": run.execute_response_json,
        "error_code": run.error_code,
        "error_message": run.error_message,
        "updated_at": _iso(run.updated_at),
    }


def _inference_item_payload(item: JobItem, thumbnail_urls: dict[str, str], inference: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "id": item.id,
        "filename": item.filename,
        "state": item.state,
        "detail": item.detail,
        "source_type": item.source_type,
        "source_id": item.source_id,
        "source_uuid": item.source_uuid,
        "thumbnail_url": thumbnail_urls.get(item.source_uuid),
        "task_id": item.task_id,
        "inference": inference,
    }


def _aggregate_inference_status(items: list[dict[str, Any]]) -> str:
    statuses = [
        item["inference"]["status"]
        for item in items
        if isinstance(item.get("inference"), dict) and item["inference"].get("status")
    ]
    if not statuses:
        return "not_configured"
    if all(status == "success" for status in statuses):
        return "complete"
    if any(status in {"running", "queued"} for status in statuses):
        return "running"
    if any(status == "pending" for status in statuses):
        return "pending"
    if any(status == "failed" for status in statuses) and any(status == "success" for status in statuses):
        return "partial"
    if any(status == "failed" for status in statuses):
        return "failed"
    return "running"


def _confidence_from_grade_comment(comment: str | None) -> float | None:
    if not comment:
        return None
    match = AI_PROBABILITY_PATTERN.search(comment)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _predicted_class_name_from_grade_comment(comment: str | None) -> str | None:
    if not comment:
        return None
    match = AI_PREDICTED_CLASS_NAME_PATTERN.search(comment)
    if not match:
        return None
    value = match.group(1).strip()
    return value or None


def get_mobile_direct_upload_thumbnail(*, db, user_id: int, upload_token: str, image_uuid: str):
    job = _scoped_job(db, user_id, upload_token)
    allowed_uuids = {item.source_uuid for item in job.items if item.source_type == "direct_image" and item.source_uuid}
    if image_uuid not in allowed_uuids:
        raise MobileUploadError("Upload image was not found.", code="image_not_found", status_code=404)
    image = db.execute(select(DirectImageUpload).where(DirectImageUpload.uuid == image_uuid)).scalar_one_or_none()
    if image is None:
        raise MobileUploadError("Upload image was not found.", code="image_not_found", status_code=404)

    try:
        thumbnail_dir, thumbnail_filename = get_direct_thumbnail_serving_path(image.folder_rel, image.filename, "orig")
        thumbnail_path = thumbnail_dir / thumbnail_filename
        if thumbnail_path.exists():
            return send_file(thumbnail_path, mimetype="image/jpeg", as_attachment=False)
    except Exception:
        current_app.logger.info("Mobile thumbnail missing for %s", sanitize_log_value(image_uuid))

    image_path = DIRECT_UPLOAD_DIR / image.folder_rel / image.filename
    if not image_path.exists():
        raise MobileUploadError("Upload image was not found.", code="image_not_found", status_code=404)
    return send_file(image_path, as_attachment=False)


def _create_direct_upload(*, db, actor: _Actor, form: MultiDict, files: MultiDict, idempotency_key: str) -> dict[str, Any]:
    profile_id = _required_int(form, "profile_id")
    project_id = _required_int(form, "project_id")
    lab_unit_id = _required_int(form, "lab_unit_id")
    disease_id = _required_int(form, "disease_id")
    camera_id = _required_int(form, "camera_id")
    area_id = _required_int(form, "area_id")
    upload_files = files.getlist("files")
    if not upload_files:
        raise MobileUploadError("At least one file is required.", code="files_required")
    try:
        result = create_direct_upload_job(
            db=db,
            actor=DirectUploadActor(user_id=actor.user_id, username=actor.username, remote_addr=actor.remote_addr),
            request=DirectUploadJobRequest(
                profile_id=profile_id,
                project_id=project_id,
                lab_unit_id=lab_unit_id,
                disease_id=disease_id,
                camera_id=camera_id,
                area_id=area_id,
                is_mydriatic=_optional_bool(form, "is_mydriatic"),
                remarks=_remarks(form.get("remarks")),
                idempotency_key=idempotency_key,
                verification_remarks=GLAUCOMA_AI_UPLOAD_VERIFICATION_REMARK,
                verification_user_id=actor.user_id,
            ),
            files=upload_files,
            upload_type="mobile direct image",
        )
    except DirectUploadJobError as exc:
        raise MobileUploadError(exc.message, code=exc.code, status_code=exc.status_code) from exc
    payload = direct_upload_response_payload(result)
    payload["_post_commit"] = {
        "kind": "direct_image",
        "user_id": actor.user_id,
        "username": actor.username,
        "remote_addr": actor.remote_addr,
        "job_token": result.job.token,
        "upload_ids": list(result.upload_ids_for_post_commit),
        "hospital_id": result.hospital_id_for_post_commit,
        "lab_unit_id": lab_unit_id,
        "project_id": project_id,
        "profile_id": profile_id,
        "inference_task_ids": list(result.inference_task_ids_for_post_commit),
    }
    return payload


def run_mobile_upload_post_commit(app, post_commit: dict[str, Any] | None) -> None:
    if not post_commit:
        return
    if post_commit.get("kind") == "remidio":
        try:
            from worker import queue_job

            queue_job(
                app,
                str(post_commit["job_token"]),
                [Path(path) for path in post_commit.get("saved_paths", [])],
                user_id=int(post_commit["user_id"]),
                hospital_id=post_commit.get("hospital_id"),
                upload_context=post_commit.get("upload_context"),
            )
        except Exception as exc:
            app.logger.warning("Could not queue mobile Remidio ZIP processing: %s", sanitize_log_value(exc))
        return

    if post_commit.get("kind") == "encounter_set":
        try:
            from services.encounter_set_ai_inference import enqueue_wadhwani_for_encounter_ids

            enqueue_wadhwani_for_encounter_ids(
                [int(post_commit["encounter_id"])],
                trigger_timing="on_image_received",
                user_id=int(post_commit["user_id"]),
                username=post_commit.get("username"),
                remote_addr=post_commit.get("remote_addr"),
            )
        except Exception as exc:
            app.logger.warning("Could not queue mobile EncounterSet inference: %s", sanitize_log_value(exc))
        return

    if post_commit.get("kind") != "direct_image":
        return
    try:
        enqueue_direct_upload_post_commit(
            app,
            user_id=int(post_commit["user_id"]),
            upload_ids=tuple(int(upload_id) for upload_id in post_commit.get("upload_ids", [])),
            job_token=str(post_commit["job_token"]),
            hospital_id=post_commit.get("hospital_id"),
        )
    except Exception as exc:
        app.logger.warning("Could not queue mobile direct upload post-processing: %s", sanitize_log_value(exc))

    task_ids = [int(task_id) for task_id in post_commit.get("inference_task_ids", []) if task_id]
    if not task_ids:
        return
    try:
        inference_job_token = db_create_job(
            [f"task:{task_id}" for task_id in task_ids],
            [],
            uploader_user_id=int(post_commit["user_id"]),
            uploader_username=post_commit.get("username"),
            uploader_ip=post_commit.get("remote_addr"),
            lab_unit_id=post_commit.get("lab_unit_id"),
            project_id=post_commit.get("project_id"),
            upload_type="mobile_direct_image_inference",
            upload_kind=UPLOAD_KIND_DIRECT_IMAGE,
            upload_profile_id=post_commit.get("profile_id"),
        )
        enqueue_task(
            "celery_tasks.tasks.wadhwani_tasks.run_wadhwani_glaucoma_batch_task",
            inference_job_token,
            task_ids,
            user_id=int(post_commit["user_id"]),
        )
    except Exception as exc:
        app.logger.warning("Could not queue mobile direct upload inference: %s", sanitize_log_value(exc))


def _create_remidio_upload(*, db, actor: _Actor, form: MultiDict, files: MultiDict, idempotency_key: str) -> dict[str, Any]:
    profile_id = _required_int(form, "profile_id")
    project_id = _required_int(form, "project_id")
    lab_unit_id = _required_int(form, "lab_unit_id")
    camera_id = _required_int(form, "camera_id")
    upload_files = files.getlist("files")
    if not upload_files:
        raise MobileUploadError("At least one ZIP file is required.", code="files_required")
    profile = validate_remedio_upload_scope(db, actor.user_id, project_id=project_id, lab_unit_id=lab_unit_id, camera_id=camera_id)
    if profile.profile_id != profile_id:
        raise MobileUploadError("Selected upload profile is not valid for this Remidio upload.", code="profile_scope_mismatch", status_code=403)
    job = _create_job(
        db,
        actor,
        upload_kind=UPLOAD_KIND_REMIDIO,
        upload_type="mobile remidio zip",
        profile_id=profile_id,
        lab_unit_id=lab_unit_id,
        project_id=project_id,
        status="queued",
        idempotency_key=idempotency_key,
    )
    accepted = 0
    rejected = 0
    saved_paths: list[str] = []
    for file in upload_files:
        valid, detail = _validate_zip_file(file)
        if valid:
            accepted += 1
            state = "queued"
            source_type = "remidio_zip"
            saved_path = _save_mobile_zip(file)
            saved_paths.append(str(saved_path))
            filename = saved_path.name
        else:
            rejected += 1
            state = "error"
            source_type = None
            filename = file.filename or "(empty filename)"
        db.add(
            JobItem(
                job_id=job.id,
                filename=filename,
                state=state,
                detail=detail,
                uploader_user_id=actor.user_id,
                uploader_username=actor.username,
                uploader_ip=actor.remote_addr,
                source_type=source_type,
            )
        )
    if accepted == 0:
        job.status = "error"
    elif rejected:
        job.status = "partial_error"
    db.flush()
    payload = _upload_response(job, upload_kind=UPLOAD_KIND_REMIDIO, accepted=accepted, rejected=rejected)
    if accepted:
        payload["_post_commit"] = {
            "kind": "remidio",
            "user_id": actor.user_id,
            "job_token": job.token,
            "saved_paths": saved_paths,
            "hospital_id": profile.hospital_id,
            "upload_context": {
                "hospital_id": profile.hospital_id,
                "lab_unit_id": profile.lab_unit_id,
                "project_id": profile.project_id,
                "upload_profile_id": profile.profile_id,
                "default_disease_id": profile.default_disease_id,
                "camera_id": camera_id,
            },
        }
    return payload


def _create_encounter_set_upload(*, db, actor: _Actor, form: MultiDict, files: MultiDict, idempotency_key: str) -> dict[str, Any]:
    profile_id = _required_int(form, "profile_id")
    project_id = _required_int(form, "project_id")
    lab_unit_id = _required_int(form, "lab_unit_id")
    payload = _encounter_json(form)
    disease_ids = [int(value) for value in payload.get("disease_ids") or ([payload["disease_id"]] if payload.get("disease_id") else [])]
    if not disease_ids:
        raise MobileUploadError("encounter_json must include disease_id or disease_ids.", code="disease_required")
    items = payload.get("items") or []
    if not items:
        raise MobileUploadError("encounter_json.items must include at least one image item.", code="items_required")
    profile = validate_profile_upload_scope(
        db,
        actor.user_id,
        profile_id=profile_id,
        upload_kind=UPLOAD_KIND_ENCOUNTER_SET,
        project_id=project_id,
        lab_unit_id=lab_unit_id,
        disease_id=disease_ids[0] if len(disease_ids) == 1 else None,
    )
    if profile.project_id != project_id or profile.lab_unit_id != lab_unit_id:
        raise MobileUploadError("Selected profile does not match project or lab unit.", code="profile_scope_mismatch", status_code=403)
    if any(disease_id not in profile.disease_ids for disease_id in disease_ids):
        raise MobileUploadError("Selected disease is not allowed for this upload profile.", code="disease_not_allowed", status_code=403)
    _require_payload_text(payload, "patient_id")
    _require_payload_text(payload, "patient_name")
    _require_payload_text(payload, "capture_date")
    referral_suggestion_raw = payload.get("referral_suggestion")
    referral_suggestion = normalize_referral_suggestion(referral_suggestion_raw)
    referral_positive_diseases = normalize_referral_positive_diseases(
        payload.get("referral_positive_diseases", payload.get("referral_positive_disease"))
    )

    encounter = PatientEncounters(
        name=payload["patient_name"],
        patient_id=payload["patient_id"],
        capture_date=payload["capture_date"],
        capture_date_dt=_parse_capture_date(payload["capture_date"]),
        lab_unit_id=lab_unit_id,
        project_id=project_id,
        upload_profile_id=profile_id,
        disease_id=disease_ids[0] if len(disease_ids) == 1 else None,
        is_set_based=True,
        remarks=_remarks(payload.get("remarks")),
        referral_suggestion=referral_suggestion,
        referral_suggestion_updated_at=utcnow() if referral_suggestion_raw is not None else None,
        referral_positive_diseases_json=referral_positive_diseases,
        uuid=str(uuid.uuid4()),
    )
    db.add(encounter)
    db.flush()
    for disease_id in disease_ids:
        db.add(PatientEncounterTargetDisease(patient_encounter_id=encounter.id, disease_id=disease_id, is_default=False))

    job = _create_job(
        db,
        actor,
        upload_kind=UPLOAD_KIND_ENCOUNTER_SET,
        upload_type="mobile encounter set",
        profile_id=profile_id,
        lab_unit_id=lab_unit_id,
        project_id=project_id,
        status="completed",
        idempotency_key=idempotency_key,
    )
    accepted = 0
    seen_positions: set[int] = set()
    for item in items:
        file_key = _require_payload_text(item, "file_key")
        spatial_position = int(item.get("spatial_position") or 0)
        if spatial_position < 1 or spatial_position > 9 or spatial_position in seen_positions:
            raise MobileUploadError("Each encounter-set image must use a unique spatial_position from 1 to 9.", code="invalid_spatial_position")
        seen_positions.add(spatial_position)
        camera_id = int(item.get("camera_id") or 0)
        area_id = int(item.get("area_id") or 0)
        is_mydriatic = _bool_value(item.get("is_mydriatic"))
        validate_profile_upload_scope(
            db,
            actor.user_id,
            profile_id=profile_id,
            upload_kind=UPLOAD_KIND_ENCOUNTER_SET,
            project_id=project_id,
            lab_unit_id=lab_unit_id,
            camera_id=camera_id,
            area_id=area_id,
            is_mydriatic=is_mydriatic,
        )
        file = files.get(file_key)
        if file is None:
            raise MobileUploadError(f"Missing multipart file part for file_key '{file_key}'.", code="file_part_missing")
        image = _save_encounter_set_image(
            file=file,
            encounter=encounter,
            project_id=project_id,
            camera_id=camera_id,
            area_id=area_id,
            spatial_position=spatial_position,
            is_mydriatic=is_mydriatic,
            remarks=_remarks(item.get("remarks")),
            referral_suggestion=_image_referral_suggestion(item),
            referral_suggestion_supplied=_image_referral_suggestion_supplied(item),
        )
        db.add(image)
        db.flush()
        accepted += 1
        db.add(
            JobItem(
                job_id=job.id,
                filename=image.original_filename,
                state="completed",
                detail="Image uploaded successfully.",
                uploader_user_id=actor.user_id,
                uploader_username=actor.username,
                uploader_ip=actor.remote_addr,
                source_type="encounter_set_image",
                source_id=image.id,
                source_uuid=image.uuid,
                finished_at=utcnow(),
            )
        )
    db.flush()
    payload = _upload_response(job, upload_kind=UPLOAD_KIND_ENCOUNTER_SET, accepted=accepted, rejected=0)
    payload["encounter_uuid"] = encounter.uuid
    payload["referral_suggestion"] = encounter.referral_suggestion
    payload["referral_positive_diseases"] = encounter.referral_positive_diseases_json or []
    payload["_post_commit"] = {
        "kind": "encounter_set",
        "user_id": actor.user_id,
        "username": actor.username,
        "remote_addr": actor.remote_addr,
        "encounter_id": encounter.id,
    }
    return payload


def _save_encounter_set_image(
    *,
    file: FileStorage,
    encounter: PatientEncounters,
    project_id: int,
    camera_id: int,
    area_id: int,
    spatial_position: int,
    is_mydriatic: bool,
    remarks: str | None,
    referral_suggestion: str = "missing",
    referral_suggestion_supplied: bool = False,
) -> EncounterSetImage:
    original = secure_filename(file.filename or "")
    if not original:
        raise MobileUploadError("Encounter-set files must have filenames.", code="invalid_filename")
    ext = Path(original).suffix.lower()
    if ext not in {".jpg", ".jpeg", ".png"}:
        raise MobileUploadError("Encounter-set files must be JPG or PNG.", code="invalid_file_type")
    image_uuid = str(uuid.uuid4())
    safe_filename = f"{image_uuid}{ext if ext in {'.jpg', '.jpeg', '.png'} else '.jpg'}"
    date_str = utcnow().strftime("%Y_%m_%d")
    folder_rel = f"files/encounter_sets/{date_str}/{encounter.id}"
    save_dir = Path(current_app.root_path) / folder_rel
    save_dir.mkdir(parents=True, exist_ok=True)
    file.save(str(save_dir / safe_filename))
    return EncounterSetImage(
        uuid=image_uuid,
        patient_encounter_id=encounter.id,
        spatial_position=spatial_position,
        original_filename=original,
        edited_filename=safe_filename,
        folder_rel=folder_rel,
        project_id=project_id,
        camera_id=camera_id,
        area_id=area_id,
        is_mydriatic=is_mydriatic,
        remarks=remarks,
        referral_needed_or_positive_image=referral_suggestion,
        referral_needed_or_positive_image_updated_at=utcnow() if referral_suggestion_supplied else None,
        created_at=utcnow(),
    )


def _image_referral_suggestion(item: dict[str, Any]) -> str:
    return normalize_referral_suggestion(_image_referral_raw(item))


def _image_referral_suggestion_supplied(item: dict[str, Any]) -> bool:
    return _image_referral_raw(item) is not None


def _image_referral_raw(item: dict[str, Any]) -> Any:
    if "referral_needed_or_positive_image" in item:
        return item.get("referral_needed_or_positive_image")
    return item.get("refrralneed_or_positive_image")


def _create_job(
    db,
    actor: _Actor,
    *,
    upload_kind: str,
    upload_type: str,
    profile_id: int,
    lab_unit_id: int,
    project_id: int,
    status: str,
    idempotency_key: str,
) -> Job:
    job = Job(
        token=str(uuid.uuid4()),
        status=status,
        upload_type=upload_type,
        upload_kind=upload_kind,
        upload_profile_id=profile_id,
        uploader_user_id=actor.user_id,
        uploader_username=actor.username,
        uploader_ip=actor.remote_addr,
        lab_unit_id=lab_unit_id,
        project_id=project_id,
        idempotency_key=idempotency_key,
    )
    db.add(job)
    db.flush()
    return job


def _upload_response(
    job: Job,
    *,
    upload_kind: str,
    accepted: int,
    rejected: int,
    uploaded: int | None = None,
    duplicates: int = 0,
) -> dict[str, Any]:
    uploaded_count = accepted if uploaded is None else uploaded
    return {
        "upload_token": job.token,
        "upload_kind": upload_kind,
        "profile_id": job.upload_profile_id,
        "status": job.status,
        "uploaded_count": uploaded_count,
        "duplicate_count": duplicates,
        "accepted_count": accepted,
        "rejected_count": rejected,
        "inference_available": False,
    }


def _upload_response_from_job(job: Job) -> dict[str, Any]:
    uploaded = sum(1 for item in job.items if item.state in {"completed", "queued", "running"})
    duplicates = sum(1 for item in job.items if item.state == "duplicate")
    accepted = uploaded + duplicates
    rejected = sum(1 for item in job.items if item.state == "error")
    payload = _upload_response(
        job,
        upload_kind=job.upload_kind or "",
        accepted=accepted,
        rejected=rejected,
        uploaded=uploaded,
        duplicates=duplicates,
    )
    payload["_replayed"] = True
    return payload


def _job_payload(job: Job) -> dict[str, Any]:
    thumbnail_urls = _available_direct_thumbnail_urls(job)
    return {
        "upload_token": job.token,
        "upload_kind": job.upload_kind,
        "profile_id": job.upload_profile_id,
        "status": job.status,
        "error": job.error,
        "rejected_summary": job.rejected_summary,
        "created_at": _iso(job.created_at),
        "updated_at": _iso(job.updated_at),
        "items": [
            {
                "id": item.id,
                "filename": item.filename,
                "state": item.state,
                "detail": item.detail,
                "source_type": item.source_type,
                "source_id": item.source_id,
                "source_uuid": item.source_uuid,
                "thumbnail_url": thumbnail_urls.get(item.source_uuid),
                "task_id": item.task_id,
                "started_at": _iso(item.started_at),
                "finished_at": _iso(item.finished_at),
            }
            for item in job.items
        ],
    }


def _available_direct_thumbnail_urls(job: Job) -> dict[str, str]:
    image_ids = {
        item.source_id
        for item in job.items
        if item.source_type == "direct_image" and item.source_id and item.source_uuid
    }
    if not image_ids:
        return {}
    db = object_session(job)
    if db is None:
        return {}
    images = (
        db.execute(
            select(DirectImageUpload).where(DirectImageUpload.id.in_(image_ids))
        )
        .scalars()
        .all()
    )
    urls: dict[str, str] = {}
    for image in images:
        if not _direct_image_available(image):
            continue
        urls[image.uuid] = f"/api/mobile/v1/uploads/{job.token}/images/{image.uuid}/thumbnail"
    return urls


def _direct_image_available(image: DirectImageUpload) -> bool:
    try:
        thumbnail_dir, thumbnail_filename = get_direct_thumbnail_serving_path(
            image.folder_rel, image.filename, "orig"
        )
        if (thumbnail_dir / thumbnail_filename).exists():
            return True
    except Exception:
        logger.debug("Unable to resolve thumbnail path for direct image %s", sanitize_log_value(image.uuid), exc_info=True)
    return (DIRECT_UPLOAD_DIR / image.folder_rel / image.filename).exists()


def _scoped_job(db, user_id: int, upload_token: str) -> Job:
    job = db.execute(select(Job).where(Job.token == upload_token)).scalar_one_or_none()
    if job is None or job.uploader_user_id != user_id:
        raise MobileUploadError("Upload was not found.", code="upload_not_found", status_code=404)
    return job


def _job_by_idempotency_key(db, *, user_id: int, idempotency_key: str) -> Job | None:
    return db.execute(
        select(Job).where(Job.uploader_user_id == user_id, Job.idempotency_key == idempotency_key)
    ).scalar_one_or_none()


def _actor(db, user_id: int, remote_addr: str | None) -> _Actor:
    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if user is None or not user.is_active:
        raise MobileUploadError("User is inactive.", code="inactive_user", status_code=403)
    if not user.has_role("fileUploader"):
        raise MobileUploadError("Uploads require the fileUploader role.", code="forbidden", status_code=403)
    return _Actor(user_id=user.id, username=user.username, remote_addr=remote_addr)


def _validate_zip_file(file: FileStorage) -> tuple[bool, str]:
    filename = file.filename or ""
    if not filename.lower().endswith(".zip"):
        return False, "Only ZIP files are accepted for Remidio upload."
    data = file.read()
    file.seek(0)
    if not data:
        return False, "ZIP file is empty."
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            names = [name for name in archive.namelist() if name and not name.endswith("/") and not name.startswith("__MACOSX/")]
            if not names:
                return False, "ZIP file does not contain upload files."
            for name in names:
                parts = Path(name).parts
                if Path(name).is_absolute() or ".." in parts:
                    return False, "ZIP file contains unsafe paths."
                if Path(name).suffix.lower() not in {".jpg", ".jpeg", ".pdf"}:
                    return False, "Remidio ZIP files may contain only JPG/JPEG/PDF files."
    except zipfile.BadZipFile:
        return False, "Invalid ZIP file."
    return True, "ZIP queued for processing."


def _save_mobile_zip(file: FileStorage) -> Path:
    date_str = datetime.now(timezone.utc).strftime("%Y_%m_%d")
    save_dir = UPLOAD_DIR / date_str
    save_dir.mkdir(parents=True, exist_ok=True)
    filename = secure_filename(file.filename or f"{uuid.uuid4().hex}.zip")
    target = save_dir / filename
    if target.exists():
        target = save_dir / f"{target.stem}-{uuid.uuid4().hex[:8]}{target.suffix}"
    file.save(str(target))
    return target


def _encounter_json(form: MultiDict) -> dict[str, Any]:
    raw = form.get("encounter_json")
    if not raw:
        raise MobileUploadError("encounter_json is required.", code="encounter_json_required")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MobileUploadError("encounter_json must be valid JSON.", code="invalid_encounter_json") from exc
    if not isinstance(payload, dict):
        raise MobileUploadError("encounter_json must be a JSON object.", code="invalid_encounter_json")
    return payload


def _remarks(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) > MAX_REMARKS_LENGTH:
        raise MobileUploadError(f"Remarks must be {MAX_REMARKS_LENGTH} characters or fewer.", code="remarks_too_long")
    if any(ord(ch) < 32 and ch not in "\n\t\r" for ch in text):
        raise MobileUploadError("Remarks contain unsupported control characters.", code="invalid_remarks")
    return text


def _required_int(form: MultiDict, name: str) -> int:
    value = form.get(name)
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise MobileUploadError(f"{name} is required and must be an integer.", code=f"{name}_required") from exc
    if parsed <= 0:
        raise MobileUploadError(f"{name} must be a positive integer.", code=f"{name}_required")
    return parsed


def _required_text(form: MultiDict, name: str) -> str:
    value = (form.get(name) or "").strip()
    if not value:
        raise MobileUploadError(f"{name} is required.", code=f"{name}_required")
    return value


def _require_payload_text(payload: dict[str, Any], name: str) -> str:
    value = str(payload.get(name) or "").strip()
    if not value:
        raise MobileUploadError(f"{name} is required.", code=f"{name}_required")
    return value


def _optional_bool(form: MultiDict, name: str) -> bool | None:
    if name not in form:
        return None
    return _bool_value(form.get(name))


def _bool_value(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _parse_capture_date(value: str):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _filter_options(items: list[dict[str, Any]], ids: set[int]) -> list[dict[str, Any]]:
    return [item for item in items if item["id"] in ids]


def _executable_ai_model_ids(db) -> set[int]:
    return {
        int(model_id)
        for model_id in db.execute(
            select(AIModelIntegration.ai_model_id)
            .where(AIModelIntegration.provider == WADHWANI_PROVIDER)
            .where(AIModelIntegration.is_enabled.is_(True))
        ).scalars()
    }


def _profile_has_executable_workflow(db, profile, *, disease_id: int, upload_kind: str) -> bool:
    executable_model_ids = _executable_ai_model_ids(db)
    return any(
        workflow.get("active", True)
        and workflow.get("upload_kind") == upload_kind
        and workflow.get("disease_id") == disease_id
        and int(workflow.get("ai_model_id") or 0) in executable_model_ids
        for workflow in profile.ai_workflows
    )


def _iso(value) -> str | None:
    return value.isoformat() + "Z" if value else None
