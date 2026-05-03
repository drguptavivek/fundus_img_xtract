from __future__ import annotations

import json
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

from flask import current_app
from sqlalchemy import select
from werkzeug.datastructures import FileStorage, MultiDict
from werkzeug.utils import secure_filename

from auth.utils import utcnow
from models import AIInferenceRun, AIModelIntegration, EncounterSetImage, Job, JobItem, PatientEncounters, User
from services.direct_upload_service import (
    DirectUploadSelection,
    create_direct_upload_batch,
    create_unverified_direct_upload_task_batch,
)
from services.wadhwani_glaucoma_inference import WADHWANI_PROVIDER
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


MOBILE_UPLOAD_KINDS = {UPLOAD_KIND_DIRECT_IMAGE, UPLOAD_KIND_REMIDIO, UPLOAD_KIND_ENCOUNTER_SET}
MAX_REMARKS_LENGTH = 1000


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
    upload_kind = _required_text(form, "upload_kind")
    if upload_kind == UPLOAD_KIND_PREGRADED:
        raise MobileUploadError("Pregraded uploads are webapp-only.", code="unsupported_upload_kind")
    if upload_kind not in MOBILE_UPLOAD_KINDS:
        raise MobileUploadError("Unsupported upload kind.", code="unsupported_upload_kind")

    if upload_kind == UPLOAD_KIND_DIRECT_IMAGE:
        return _create_direct_upload(db=db, actor=actor, form=form, files=files)
    if upload_kind == UPLOAD_KIND_REMIDIO:
        return _create_remidio_upload(db=db, actor=actor, form=form, files=files)
    return _create_encounter_set_upload(db=db, actor=actor, form=form, files=files)


def get_mobile_upload_status(*, db, user_id: int, upload_token: str) -> dict[str, Any]:
    job = _scoped_job(db, user_id, upload_token)
    return _job_payload(job)


def get_mobile_upload_inference(*, db, user_id: int, upload_token: str) -> dict[str, Any]:
    job = _scoped_job(db, user_id, upload_token)
    task_ids = [item.task_id for item in job.items if item.task_id]
    if not task_ids:
        return {"upload_token": job.token, "status": "not_configured", "results": []}
    runs = (
        db.execute(
            select(AIInferenceRun)
            .where(AIInferenceRun.task_id.in_(task_ids))
            .order_by(AIInferenceRun.created_at.desc(), AIInferenceRun.id.desc())
        )
        .scalars()
        .all()
    )
    if not runs:
        return {"upload_token": job.token, "status": "pending", "results": []}
    status = "complete" if all(run.status == "success" for run in runs) else "failed" if any(run.status == "failed" for run in runs) else "running"
    return {
        "upload_token": job.token,
        "status": status,
        "results": [
            {
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
            for run in runs
        ],
    }


def _create_direct_upload(*, db, actor: _Actor, form: MultiDict, files: MultiDict) -> dict[str, Any]:
    profile_id = _required_int(form, "profile_id")
    project_id = _required_int(form, "project_id")
    lab_unit_id = _required_int(form, "lab_unit_id")
    disease_id = _required_int(form, "disease_id")
    camera_id = _required_int(form, "camera_id")
    area_id = _required_int(form, "area_id")
    upload_files = files.getlist("files")
    if not upload_files:
        raise MobileUploadError("At least one file is required.", code="files_required")
    remarks = _remarks(form.get("remarks"))
    profile = validate_profile_upload_scope(
        db,
        actor.user_id,
        profile_id=profile_id,
        upload_kind=UPLOAD_KIND_DIRECT_IMAGE,
        disease_id=disease_id,
        camera_id=camera_id,
        area_id=area_id,
        is_mydriatic=_optional_bool(form, "is_mydriatic"),
    )
    if profile.project_id != project_id or profile.lab_unit_id != lab_unit_id:
        raise MobileUploadError("Selected profile does not match project or lab unit.", code="profile_scope_mismatch", status_code=403)
    is_mydriatic = _optional_bool(form, "is_mydriatic")
    if is_mydriatic is None:
        is_mydriatic = profile.default_is_mydriatic
    executable_workflow = _profile_has_executable_workflow(db, profile, disease_id=disease_id, upload_kind=UPLOAD_KIND_DIRECT_IMAGE)
    batch_factory = create_unverified_direct_upload_task_batch if executable_workflow else create_direct_upload_batch
    result = batch_factory(
        db=db,
        files=upload_files,
        user_id=actor.user_id,
        selection=DirectUploadSelection(
            project_id=project_id,
            lab_unit_id=lab_unit_id,
            disease_id=disease_id,
            camera_id=camera_id,
            area_id=area_id,
            is_mydriatic=is_mydriatic,
            profile_id=profile_id,
        ),
        remarks=remarks,
    )
    job = _create_job(
        db,
        actor,
        upload_kind=UPLOAD_KIND_DIRECT_IMAGE,
        upload_type="mobile direct image",
        profile_id=profile.profile_id,
        lab_unit_id=lab_unit_id,
        project_id=project_id,
        status="completed" if result.error_count == 0 else "partial_error",
    )
    for item in result.items:
        db.add(
            JobItem(
                job_id=job.id,
                filename=item.filename,
                state="completed" if item.status == "success" else "error",
                detail=item.message,
                uploader_user_id=actor.user_id,
                uploader_username=actor.username,
                uploader_ip=actor.remote_addr,
                source_type="direct_image",
                source_id=item.upload_id,
                source_uuid=item.image_uuid,
                task_id=item.task_id,
                finished_at=utcnow(),
            )
        )
    db.flush()
    payload = _upload_response(job, upload_kind=UPLOAD_KIND_DIRECT_IMAGE, accepted=result.success_count, rejected=result.error_count)
    payload["inference_available"] = executable_workflow and any(item.task_id for item in result.items)
    return payload


def _create_remidio_upload(*, db, actor: _Actor, form: MultiDict, files: MultiDict) -> dict[str, Any]:
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
    )
    accepted = 0
    rejected = 0
    for file in upload_files:
        valid, detail = _validate_zip_file(file)
        if valid:
            accepted += 1
            state = "queued"
            source_type = "remidio_zip"
            filename = _save_mobile_zip(file)
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
    return _upload_response(job, upload_kind=UPLOAD_KIND_REMIDIO, accepted=accepted, rejected=rejected)


def _create_encounter_set_upload(*, db, actor: _Actor, form: MultiDict, files: MultiDict) -> dict[str, Any]:
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
        disease_id=disease_ids[0] if len(disease_ids) == 1 else None,
    )
    if profile.project_id != project_id or profile.lab_unit_id != lab_unit_id:
        raise MobileUploadError("Selected profile does not match project or lab unit.", code="profile_scope_mismatch", status_code=403)
    if any(disease_id not in profile.disease_ids for disease_id in disease_ids):
        raise MobileUploadError("Selected disease is not allowed for this upload profile.", code="disease_not_allowed", status_code=403)
    _require_payload_text(payload, "patient_id")
    _require_payload_text(payload, "patient_name")
    _require_payload_text(payload, "capture_date")

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
    return payload


def _save_encounter_set_image(*, file: FileStorage, encounter: PatientEncounters, project_id: int, camera_id: int, area_id: int, spatial_position: int, is_mydriatic: bool, remarks: str | None) -> EncounterSetImage:
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
        created_at=utcnow(),
    )


def _create_job(db, actor: _Actor, *, upload_kind: str, upload_type: str, profile_id: int, lab_unit_id: int, project_id: int, status: str) -> Job:
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
    )
    db.add(job)
    db.flush()
    return job


def _upload_response(job: Job, *, upload_kind: str, accepted: int, rejected: int) -> dict[str, Any]:
    return {
        "upload_token": job.token,
        "upload_kind": upload_kind,
        "profile_id": job.upload_profile_id,
        "status": job.status,
        "accepted_count": accepted,
        "rejected_count": rejected,
        "inference_available": False,
    }


def _job_payload(job: Job) -> dict[str, Any]:
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
                "task_id": item.task_id,
                "started_at": _iso(item.started_at),
                "finished_at": _iso(item.finished_at),
            }
            for item in job.items
        ],
    }


def _scoped_job(db, user_id: int, upload_token: str) -> Job:
    job = db.execute(select(Job).where(Job.token == upload_token)).scalar_one_or_none()
    if job is None or job.uploader_user_id != user_id:
        raise MobileUploadError("Upload was not found.", code="upload_not_found", status_code=404)
    return job


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


def _save_mobile_zip(file: FileStorage) -> str:
    date_str = datetime.now(timezone.utc).strftime("%Y_%m_%d")
    save_dir = Path(current_app.root_path) / "files" / "mobile_remidio_zips" / date_str
    save_dir.mkdir(parents=True, exist_ok=True)
    filename = secure_filename(file.filename or f"{uuid.uuid4().hex}.zip")
    target = save_dir / filename
    if target.exists():
        target = save_dir / f"{target.stem}-{uuid.uuid4().hex[:8]}{target.suffix}"
    file.save(str(target))
    return target.name


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
