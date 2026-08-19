"""Encounter-scoped MadhuNetrAI DR-DME eligibility, execution, and reconciliation."""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from auth.utils import utcnow
from db_transaction_manager import transaction_scope
from models import (
    AIModelIntegration,
    BASE_DIR,
    DiseaseGrading,
    EncounterSetImage,
    Grade,
    GradingTask,
    PatientEncounters,
    User,
)
from remote_inference.models import (
    EncounterAIImageResult,
    EncounterAIInferenceRun,
    EncounterAIOutputTarget,
    EncounterAITargetResult,
    ProjectEncounterAIWorkflow,
)
from services.madhunetra_client import MadhuNetrAIClient, MadhuNetrAIError


PROVIDER = "wai_dr_dme"
WORKFLOW_KEY = "dr_dme"
MODEL_NAME = "madhunetra_17aug2026"
MODEL_VERSION = "17aug2026"
DEFAULT_CONFIG = {
    "similarity_ungradable_threshold": 80.0,
    "maximum_images_per_eye": 10,
    "upload_retry_delays_seconds": [3, 5],
    "submit_timeout_seconds": 180,
    "mapping_version": "17aug2026",
    "normalization_version": "v1",
}


class EncounterInferenceError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class EligibleImage:
    image_id: int
    image_uuid: str
    filename: str
    eye: str
    content_type: str


@dataclass(frozen=True)
class EncounterEligibility:
    eligible: bool
    issues: tuple[str, ...]
    images: tuple[EligibleImage, ...]
    is_verified: bool
    is_monocular: bool
    age: int | None
    sex: str | None

    @property
    def eye_counts(self) -> dict[str, int]:
        return {eye: sum(row.eye == eye for row in self.images) for eye in ("right", "left")}


@dataclass(frozen=True)
class EncounterInferenceResult:
    run_id: int
    request_id: str
    report_id: str | None
    status: str
    reused: bool = False


def normalize_eye(value: Any) -> str | None:
    normalized = str(value or "").strip().lower().replace("_", " ")
    if normalized in {"od", "r", "right", "right eye"}:
        return "right"
    if normalized in {"os", "l", "left", "left eye"}:
        return "left"
    return None


def normalize_focus(value: Any) -> str | None:
    normalized = str(value or "").strip().lower().replace("_", " ")
    if normalized in {"macula", "macular", "macula centred", "macula centered", "posterior pole"}:
        return "macula"
    if normalized in {"disc", "disk", "onh", "optic disc", "optic nerve head"}:
        return "disc"
    return None


def _metadata_value(metadata: dict[str, Any], *keys: str) -> Any:
    lowered = {str(key).lower(): value for key, value in metadata.items()}
    for key in keys:
        if key.lower() in lowered and lowered[key.lower()] not in (None, ""):
            return lowered[key.lower()]
    for value in metadata.values():
        if isinstance(value, dict):
            found = _metadata_value(value, *keys)
            if found not in (None, ""):
                return found
    return None


DEFAULT_PATIENT_METADATA_MAPPING = {
    "patient_id": "__encounter_patient_id__",
    "age": "patient_age_yrs",
    "sex": "sex",
    "is_monocular": "is_monocular",
}


def _patient_metadata_mapping(encounter: PatientEncounters) -> dict[str, str]:
    return DEFAULT_PATIENT_METADATA_MAPPING


def _patient_value(encounter: PatientEncounters, role: str, *fallback_keys: str) -> Any:
    metadata = encounter.metadata_json if isinstance(encounter.metadata_json, dict) else {}
    field_key = _patient_metadata_mapping(encounter).get(role)
    if role == "patient_id" and field_key == "__encounter_patient_id__":
        if encounter.patient_id not in (None, ""):
            return encounter.patient_id
    if field_key:
        value = _metadata_value(metadata, field_key)
        if value not in (None, ""):
            return value
    return _metadata_value(metadata, *fallback_keys)


def _content_type(filename: str) -> str | None:
    suffix = Path(filename).suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".png":
        return "image/png"
    return None


def evaluate_encounter(encounter: PatientEncounters, *, require_verified: bool = False) -> EncounterEligibility:
    issues: list[str] = []
    is_verified = str(encounter.encounter_verified_status or "").lower() == "verified"
    is_monocular = _patient_value(encounter, "is_monocular", "is_monocular") is True
    if require_verified and not is_verified:
        issues.append("EncounterSet is not verified.")
    patient_id = str(_patient_value(encounter, "patient_id", "hospital_UHID", "mrn", "uhid") or "")
    if not patient_id or len(patient_id) > 30:
        issues.append("Patient identifier must contain 1 to 30 characters.")
    try:
        parsed_age = int(_patient_value(encounter, "age", "patient_age_yrs", "age", "patient_age", "age_yrs"))
    except (TypeError, ValueError):
        parsed_age = -1
    age = parsed_age if 0 <= parsed_age <= 120 else None
    if age is None:
        issues.append("Patient age must be between 0 and 120.")
    parsed_sex = str(_patient_value(encounter, "sex", "sex", "gender") or "").strip().lower()
    sex = parsed_sex if parsed_sex in {"male", "female", "other"} else None
    if sex is None:
        issues.append("Patient sex must be male, female, or other.")

    selected: list[EligibleImage] = []
    for image in sorted(encounter.encounter_set_images, key=lambda row: (row.spatial_position, row.id)):
        if (
            image.asset_kind != "clinical_image"
            or not image.creates_task
            or not getattr(image, "visible_to_grader", True)
        ):
            continue
        image_metadata = image.metadata_json if isinstance(image.metadata_json, dict) else {}
        eye = normalize_eye(_metadata_value(image_metadata, "laterality", "eye", "eye_side"))
        focus = normalize_focus(_metadata_value(image_metadata, "focus", "centering", "fundus_field"))
        if eye is None or focus != "macula":
            continue
        filename = image.edited_filename or image.original_filename
        content_type = _content_type(filename)
        if content_type is None:
            issues.append(f"Image {image.uuid} is not JPEG or PNG.")
            continue
        selected.append(EligibleImage(image.id, image.uuid, filename, eye, content_type))
    if not selected:
        issues.append("No macula-focused image has unambiguous laterality.")
    eye_counts = {eye: sum(row.eye == eye for row in selected) for eye in ("left", "right")}
    if selected and 0 in eye_counts.values() and not is_monocular:
        issues.append("Both eyes require a macula image unless the patient is marked monocular.")
    for eye in ("left", "right"):
        if eye_counts[eye] > 10:
            issues.append(f"More than 10 {eye}-eye images are present; the encounter cannot be split or truncated.")
    return EncounterEligibility(
        eligible=not issues,
        issues=tuple(issues),
        images=tuple(selected),
        is_verified=is_verified,
        is_monocular=is_monocular,
        age=age,
        sex=sex,
    )


def has_completed_dr_ocr(encounter: PatientEncounters) -> bool:
    """Require a completed local OCR result with normalized ``ocr.dr_report``."""
    for attachment in encounter.encounter_set_attachments:
        metadata = attachment.metadata_json if isinstance(attachment.metadata_json, dict) else {}
        ocr = metadata.get("ocr") if isinstance(metadata.get("ocr"), dict) else {}
        if str(ocr.get("status") or "").lower() in {"completed", "success", "ok"} and ocr.get("dr_report"):
            return True
    return False


def workflow_allows_automatic(workflow: ProjectEncounterAIWorkflow, encounter: PatientEncounters) -> bool:
    if not workflow.active or not workflow.automatic_enabled:
        return False
    if workflow.automatic_eligibility == "always":
        return True
    return workflow.automatic_eligibility == "if_dr_ocr_report_present" and has_completed_dr_ocr(encounter)


def _patient_payload(encounter: PatientEncounters) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "patient_id": str(_patient_value(encounter, "patient_id", "hospital_UHID", "mrn", "uhid")),
        "age": int(_patient_value(encounter, "age", "patient_age_yrs", "age", "patient_age", "age_yrs")),
    }
    sex = str(_patient_value(encounter, "sex", "sex", "gender") or "").strip().lower()
    if sex in {"male", "female", "other"}:
        payload["sex"] = sex
    if _patient_value(encounter, "is_monocular", "is_monocular") is True:
        payload["is_monocular"] = True
    return payload


def _find_local_grading(db, disease_id: int, mapped: str) -> DiseaseGrading | None:
    grading = db.execute(
        select(DiseaseGrading).where(
            DiseaseGrading.disease_id == disease_id,
            func.lower(DiseaseGrading.impression) == mapped.lower(),
            DiseaseGrading.is_active.is_(True),
        )
    ).scalar_one_or_none()
    if grading is None and mapped == "Not Gradable":
        grading = db.execute(
            select(DiseaseGrading).where(
                DiseaseGrading.disease_id == disease_id,
                DiseaseGrading.is_ungradable.is_(True),
                DiseaseGrading.is_active.is_(True),
            )
        ).scalars().first()
    return grading


def _validate_output_mappings(db, ai_model_id: int) -> None:
    """Fail before contacting the provider when a local grade mapping is stale."""
    targets = db.execute(
        select(EncounterAIOutputTarget).where(
            EncounterAIOutputTarget.ai_model_id == ai_model_id,
            EncounterAIOutputTarget.active.is_(True),
        )
    ).scalars().all()
    if {target.target_key for target in targets} != {"dr", "dme"}:
        raise EncounterInferenceError("target_mapping_invalid", "Active DR and DME output mappings are required.")
    for target in targets:
        for mapped in set((target.label_mapping_json or {}).values()):
            if not isinstance(mapped, str) or not mapped.strip():
                raise EncounterInferenceError(
                    "grade_mapping_invalid",
                    f"The {target.target_key.upper()} output mapping contains an empty local grade.",
                )
            if _find_local_grading(db, target.disease_id, mapped) is None:
                raise EncounterInferenceError(
                    "grade_mapping_invalid",
                    f"Configured local grade {mapped!r} does not exist.",
                )


def _read_image_bytes(image: EncounterSetImage, filename: str) -> bytes:
    s3_key = image.s3_object_key_edited if image.edited_filename and filename == image.edited_filename else image.s3_object_key
    if image.s3_config and s3_key:
        from utils.s3_prefix import apply_global_prefix
        from utils.s3_storage_backends import get_s3_client

        response = get_s3_client(image.s3_config).get_object(
            Bucket=image.s3_config.bucket_name, Key=apply_global_prefix(s3_key)
        )
        value = response["Body"].read()
    else:
        path = BASE_DIR / image.folder_rel / filename
        if not path.exists():
            raise EncounterInferenceError("image_not_found", f"Image {image.uuid} is missing from storage.")
        value = path.read_bytes()
    try:
        with Image.open(BytesIO(value)) as opened:
            detected = opened.format
            opened.verify()
    except Exception as exc:
        raise EncounterInferenceError("invalid_image", f"Image {image.uuid} is not a valid JPEG or PNG.") from exc
    if detected not in {"JPEG", "PNG"}:
        raise EncounterInferenceError("invalid_image", f"Image {image.uuid} is not a valid JPEG or PNG.")
    return value


def _sanitized_presign(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "request_id": payload.get("request_id"),
        "uploads": [
            {key: row.get(key) for key in ("eye", "key", "original_filename", "content_type")}
            for row in payload.get("uploads") or []
            if isinstance(row, dict)
        ],
    }


def run_encounter_inference(
    *,
    encounter_id: int,
    requested_by_user_id: int | None = None,
    source: str = "automatic",
    client: MadhuNetrAIClient | None = None,
) -> EncounterInferenceResult:
    """Execute or reconcile exactly one durable screening for an encounter."""
    with transaction_scope() as db:
        integration = db.execute(
            select(AIModelIntegration)
            .options(selectinload(AIModelIntegration.ai_model))
            .where(AIModelIntegration.provider == PROVIDER, AIModelIntegration.is_enabled.is_(True))
        ).scalar_one_or_none()
        if integration is None:
            raise EncounterInferenceError("integration_not_configured", "MadhuNetrAI DR-DME integration is not enabled.")
        encounter = db.execute(
            select(PatientEncounters)
            .options(
                selectinload(PatientEncounters.encounter_set_images).selectinload(EncounterSetImage.s3_config),
                selectinload(PatientEncounters.encounter_set_attachments),
            )
            .where(PatientEncounters.id == encounter_id)
        ).scalar_one_or_none()
        if encounter is None:
            raise EncounterInferenceError("encounter_not_found", "EncounterSet was not found.")
        eligibility = evaluate_encounter(encounter, require_verified=source == "manual")
        if not eligibility.eligible:
            raise EncounterInferenceError("ineligible_encounter", "; ".join(eligibility.issues))
        existing = db.execute(
            select(EncounterAIInferenceRun)
            .options(selectinload(EncounterAIInferenceRun.image_results))
            .where(
                EncounterAIInferenceRun.patient_encounter_id == encounter.id,
                EncounterAIInferenceRun.ai_model_id == integration.ai_model_id,
            )
        ).scalar_one_or_none()
        if existing and existing.status in {"success", "partial"}:
            return EncounterInferenceResult(existing.id, existing.request_id, existing.report_id, existing.status, True)
        _validate_output_mappings(db, integration.ai_model_id)
        config = {**DEFAULT_CONFIG, **(integration.config_json or {})}
        retrying_failed_run = existing is not None and existing.status == "failed"
        if retrying_failed_run:
            # Keep the durable run/request identity, but discard attempt-scoped
            # evidence so changed image selections cannot collide with stale rows.
            existing.image_results.clear()
            db.flush()
            existing.report_id = None
            existing.http_status = None
            existing.presign_response_json = None
            existing.submit_response_json = None
            existing.error_code = None
            existing.error_message = None
            existing.finished_at = None
        run = existing or EncounterAIInferenceRun(
            patient_encounter_id=encounter.id,
            ai_model_id=integration.ai_model_id,
            integration_id=integration.id,
            requested_by_user_id=requested_by_user_id,
            source=source,
            request_id=encounter.uuid,
        )
        run.integration_id = integration.id
        run.requested_by_user_id = requested_by_user_id
        run.source = source
        run.status = "presigning"
        run.started_at = utcnow() if retrying_failed_run else (run.started_at or utcnow())
        run.config_snapshot_json = config
        manifest = [
            {"image_id": row.image_id, "image_uuid": row.image_uuid, "original_filename": row.filename, "eye": row.eye, "content_type": row.content_type}
            for row in eligibility.images
        ]
        run.request_manifest_json = {"patient": _patient_payload(encounter), "images": manifest}
        if existing is None:
            db.add(run)
            db.flush()
        if existing is None or retrying_failed_run:
            for row in eligibility.images:
                run.image_results.append(
                    EncounterAIImageResult(encounter_set_image_id=row.image_id, submitted_eye=row.eye)
                )
        db.flush()
        run_id = run.id
        request_id = run.request_id
        integration_id = integration.id
        base_url = integration.api_base_url
        token = integration.get_access_token() if client is None else None
        image_rows = {image.id: image for image in encounter.encounter_set_images}
        image_bytes = {row.image_id: _read_image_bytes(image_rows[row.image_id], row.filename) for row in eligibility.images}
        patient_payload = _patient_payload(encounter)
        presign_images = [{"original_filename": row.filename, "eye": row.eye} for row in eligibility.images]

    remote = client or MadhuNetrAIClient(base_url=base_url or "", token=token or "")
    try:
        presigned = remote.presign(request_id=request_id, images=presign_images)
        uploads = presigned.get("uploads") or []
        if len(uploads) != len(eligibility.images):
            raise EncounterInferenceError("invalid_response", "Presign response did not return one upload per image.")
        with transaction_scope() as db:
            run = db.get(EncounterAIInferenceRun, run_id)
            run.presign_response_json = _sanitized_presign(presigned)
            run.status = "uploading"
            results = {row.encounter_set_image_id: row for row in run.image_results}
            for eligible, upload in zip(eligibility.images, uploads, strict=True):
                results[eligible.image_id].remote_key = upload.get("key")

        submit_images: list[dict[str, str]] = []
        attempt_counts: dict[int, int] = {}
        for eligible, upload in zip(eligibility.images, uploads, strict=True):
            if upload.get("eye") != eligible.eye or upload.get("content_type") != eligible.content_type or not upload.get("key"):
                raise EncounterInferenceError("invalid_response", "Presign response changed image eye, content type, or key.")
            try:
                attempt_counts[eligible.image_id] = remote.upload(
                    upload_url=str(upload["upload_url"]), content_type=eligible.content_type, image_bytes=image_bytes[eligible.image_id]
                )
            except MadhuNetrAIError as exc:
                if exc.status_code != 403:
                    raise
                refreshed = remote.presign(request_id=request_id, images=presign_images)
                refreshed_uploads = refreshed.get("uploads") or []
                refreshed_by_key = {row.get("key"): row for row in refreshed_uploads if isinstance(row, dict)}
                upload = refreshed_by_key.get(upload.get("key"))
                if not upload:
                    raise EncounterInferenceError("invalid_response", "Refreshed Presign response omitted an existing key.")
                attempt_counts[eligible.image_id] = 1 + remote.upload(
                    upload_url=str(upload["upload_url"]), content_type=eligible.content_type, image_bytes=image_bytes[eligible.image_id]
                )
            submit_images.append({"key": str(upload["key"]), "eye": eligible.eye, "original_filename": eligible.filename})

        with transaction_scope() as db:
            run = db.get(EncounterAIInferenceRun, run_id)
            run.status = "submitting"
            for result in run.image_results:
                result.upload_attempts = attempt_counts.get(result.encounter_set_image_id, 0)
        submitted = remote.submit(request_id=request_id, patient=patient_payload, images=submit_images)
        return _persist_response(run_id, submitted)
    except (MadhuNetrAIError, EncounterInferenceError) as exc:
        _mark_failed(run_id, exc)
        raise


def _persist_response(run_id: int, payload: dict[str, Any]) -> EncounterInferenceResult:
    with transaction_scope() as db:
        run = db.execute(
            select(EncounterAIInferenceRun)
            .options(selectinload(EncounterAIInferenceRun.image_results))
            .where(EncounterAIInferenceRun.id == run_id)
            .with_for_update()
        ).scalar_one()
        targets = db.execute(
            select(EncounterAIOutputTarget).where(
                EncounterAIOutputTarget.ai_model_id == run.ai_model_id,
                EncounterAIOutputTarget.active.is_(True),
            )
        ).scalars().all()
        if {target.target_key for target in targets} != {"dr", "dme"}:
            raise EncounterInferenceError("target_mapping_invalid", "Active DR and DME output mappings are required.")
        by_key = {row.remote_key: row for row in run.image_results}
        partial = False
        seen_keys: set[str] = set()
        primary_counts = {"left": 0, "right": 0}
        for eye in ("left", "right"):
            for remote_row in ((payload.get("results") or {}).get("images") or {}).get(eye, []) or []:
                image_result = by_key.get(remote_row.get("key"))
                if image_result is None:
                    raise EncounterInferenceError("invalid_response", "Submit response returned an unknown image key.")
                seen_keys.add(str(remote_row.get("key")))
                outputs = remote_row.get("model_outputs") if isinstance(remote_row.get("model_outputs"), dict) else {}
                image_result.raw_output_json = outputs
                image_result.is_primary = remote_row.get("is_primary") is True
                primary_counts[eye] += int(image_result.is_primary)
                detected = ((outputs.get("eyes") or {}).get("eyes_label") if isinstance(outputs.get("eyes"), dict) else None)
                image_result.detected_eye = detected
                image_result.laterality_mismatch = normalize_eye(detected) not in {None, image_result.submitted_eye}
                similarity = outputs.get("similarity_score")
                image_result.similarity_score = float(similarity) if similarity is not None else None
                provider_error = outputs.get("status") == "error"
                threshold = float((run.config_snapshot_json or {}).get("similarity_ungradable_threshold", 80))
                ungradable = provider_error or (image_result.similarity_score is not None and image_result.similarity_score >= threshold)
                image_result.quality_state = "error" if provider_error else ("ungradable" if ungradable else "gradable")
                partial = partial or provider_error
                drdme = outputs.get("drdme") if isinstance(outputs.get("drdme"), dict) else {}
                for target in targets:
                    raw_label = drdme.get("DR_grade" if target.target_key == "dr" else "DME_grade")
                    raw_score = drdme.get("DR_score" if target.target_key == "dr" else "DME_score")
                    derivation = "provider"
                    if provider_error:
                        mapped = "Not Gradable"
                        derivation = "provider_error"
                    elif ungradable:
                        mapped = "Not Gradable"
                        derivation = "similarity_threshold"
                    else:
                        mapped = (target.label_mapping_json or {}).get(str(raw_label))
                        if not mapped:
                            raise EncounterInferenceError("unmapped_label", f"No {target.target_key.upper()} mapping exists for {raw_label!r}.")
                    grade = _upsert_grade(db, run, image_result, target, mapped, raw_label, raw_score)
                    result = db.execute(
                        select(EncounterAITargetResult).where(
                            EncounterAITargetResult.image_result_id == image_result.id,
                            EncounterAITargetResult.output_target_id == target.id,
                        )
                    ).scalar_one_or_none()
                    if result is None:
                        result = EncounterAITargetResult(image_result_id=image_result.id, output_target_id=target.id)
                        db.add(result)
                    result.raw_label = str(raw_label) if raw_label is not None else None
                    result.raw_score = float(raw_score) if raw_score is not None else None
                    result.mapped_grade = mapped
                    result.derivation_reason = derivation
                    result.grade = grade
        if seen_keys != set(by_key):
            raise EncounterInferenceError("invalid_response", "Submit response did not return every submitted image.")
        submitted_eyes = {row.submitted_eye for row in run.image_results}
        if any(primary_counts[eye] != 1 for eye in submitted_eyes):
            raise EncounterInferenceError("invalid_response", "Submit response must identify exactly one primary image per submitted eye.")
        run.report_id = str(payload.get("report_id") or "") or None
        run.submit_response_json = payload
        run.status = "partial" if partial else "success"
        run.error_code = None
        run.error_message = None
        run.finished_at = utcnow()
        db.flush()
        return EncounterInferenceResult(run.id, run.request_id, run.report_id, run.status)


def _upsert_grade(db, run, image_result, target, mapped, raw_label, raw_score) -> Grade:
    task = db.execute(
        select(GradingTask).where(
            GradingTask.encounter_set_image_id == image_result.encounter_set_image_id,
            GradingTask.disease_id == target.disease_id,
            GradingTask.encounter_set_package_id.is_(None),
        )
    ).scalar_one_or_none()
    if task is None:
        encounter = db.get(PatientEncounters, run.patient_encounter_id)
        task = GradingTask(
            encounter_set_image_id=image_result.encounter_set_image_id,
            disease_id=target.disease_id,
            lab_unit_id=encounter.lab_unit_id,
            source_upload_profile_id=encounter.upload_profile_id,
            grading_target_level="image",
            task_source="madhunetra_dr_dme",
        )
        db.add(task)
        db.flush()
    grading = _find_local_grading(db, target.disease_id, mapped)
    if grading is None:
        raise EncounterInferenceError("grade_mapping_invalid", f"Configured local grade {mapped!r} does not exist.")
    ai_system = db.execute(select(User).where(User.username == "ai_system")).scalar_one_or_none()
    if ai_system is None:
        ai_system = User(username="ai_system", password_hash="not-used", is_active=False, full_name="AI System", designation="System")
        db.add(ai_system)
        db.flush()
    grade = db.execute(
        select(Grade).where(Grade.task_id == task.id, Grade.role_slot == "ai")
    ).scalar_one_or_none()
    if grade is None:
        grade = Grade(task_id=task.id, grader_user_id=ai_system.id, role_slot="ai", disease_grading_id=grading.id)
        db.add(grade)
    grade.grader_user_id = ai_system.id
    grade.disease_grading_id = grading.id
    grade.ai_model_id = run.ai_model_id
    grade.ai_model_name = MODEL_NAME
    grade.ai_model_version = MODEL_VERSION
    grade.disease_name = grading.disease.name
    grade.grade_name = grading.impression
    grade.grade_description = grading.guidelines
    grade.comment = f"MadhuNetrAI raw label: {raw_label}; raw score: {raw_score}; request_id: {run.request_id}"
    return grade


def _mark_failed(run_id: int, exc: Exception) -> None:
    with transaction_scope() as db:
        run = db.get(EncounterAIInferenceRun, run_id)
        if run is None:
            return
        run.status = "failed"
        run.error_code = getattr(exc, "code", "unexpected_error")
        run.error_message = str(exc)
        run.http_status = getattr(exc, "status_code", None)
        run.finished_at = utcnow()
