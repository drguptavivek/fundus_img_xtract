"""Scoped non-PII EncounterSet exports for the project workspace."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import selectinload

from authz.project_access import allowed_project_lab_unit_ids
from datasets.annotation_export import (
    write_annotation_export,
    write_annotator_exports,
    write_coco_exports,
)
from db_transaction_manager import get_db_session
from encounter_sets.export_service import (
    _xlsx_value,
    collect_non_pii_metadata_headers,
    non_pii_metadata_values,
)
from job_store import db_set_item_state, db_set_job_status
from models import (
    BASE_DIR,
    Consensus,
    EncounterSetImage,
    Grade,
    GradingTask,
    Job,
    PatientEncounters,
    Project,
    User,
)
from remote_inference.encounter_service import is_positive_output
from remote_inference.models import (
    ProjectAutomatedRemoteInferenceRule,
    ProjectEncounterAIWorkflow,
    ProjectManualRemoteInferenceWorkflow,
)
from review.discrepancy_export import EXPORT_DIR, _write_zips


EXPORT_KINDS = frozenset({"workbook", "images"})
GRADING_FILTERS = frozenset({"all", "any_graded", "completed"})
MAX_IMAGE_EXPORT_ENCOUNTERS = 250


@dataclass(frozen=True)
class ProjectExportRequest:
    project_id: int
    actor_user_id: int
    kind: str
    date_from: date | None
    date_to: date | None
    grading_filter: str


@dataclass(frozen=True)
class ProjectExportHistoryItem:
    token: str
    status: str
    created_at: datetime | None
    updated_at: datetime | None
    files: tuple[str, ...]


def validate_export_request(
    *, project_id: int, actor_user_id: int, kind: str,
    date_from: date | None, date_to: date | None, grading_filter: str,
) -> ProjectExportRequest:
    if kind not in EXPORT_KINDS:
        raise ValueError("Invalid export type.")
    if grading_filter not in GRADING_FILTERS:
        raise ValueError("Invalid grading filter.")
    if date_from and date_to and date_from > date_to:
        raise ValueError("The start date must be on or before the end date.")
    return ProjectExportRequest(project_id, actor_user_id, kind, date_from, date_to, grading_filter)


def authorized_project_export_labs(db, *, actor: User, project_id: int) -> frozenset[int]:
    project = db.get(Project, project_id)
    if project is None or not project.active:
        return frozenset()
    return allowed_project_lab_unit_ids(
        db, actor, project_id=project_id, roles={"data_manager"}
    )


def run_project_export_job(job_token: str, request_data: dict[str, Any]) -> None:
    db_set_job_status(job_token, "processing")
    db_set_item_state(job_token, "project_export", "processing")
    try:
        request = validate_export_request(
            project_id=int(request_data["project_id"]),
            actor_user_id=int(request_data["actor_user_id"]),
            kind=str(request_data["kind"]),
            date_from=date.fromisoformat(request_data["date_from"]) if request_data.get("date_from") else None,
            date_to=date.fromisoformat(request_data["date_to"]) if request_data.get("date_to") else None,
            grading_filter=str(request_data["grading_filter"]),
        )
        with get_db_session() as db:
            actor = db.get(User, request.actor_user_id)
            if request_data.get("sync_grant_uuid"):
                # Desktop mirror export: authority is the approved sync grant,
                # re-derived now in case it was revoked while queued.
                from project_sync.service import grant_export_scope

                allowed_labs, grant_pii_labs = grant_export_scope(
                    db,
                    grant_uuid=str(request_data["sync_grant_uuid"]),
                    user_id=request.actor_user_id,
                    project_id=request.project_id,
                )
            else:
                grant_pii_labs = frozenset()
                allowed_labs = (
                    authorized_project_export_labs(db, actor=actor, project_id=request.project_id)
                    if actor else frozenset()
                )
            if not allowed_labs:
                raise PermissionError("Project export authority is no longer available")
            encounters = _encounters(db, request, allowed_labs)
            if request.kind == "images" and len(encounters) > MAX_IMAGE_EXPORT_ENCOUNTERS:
                raise ValueError(
                    f"Image exports are limited to 250 EncounterSets; the current filters match {len(encounters)}."
                )
            encounter_ids = [item.id for item in encounters]
            images = _images(db, encounter_ids)
            tasks = _tasks(db, encounter_ids)

            export_dir = EXPORT_DIR / job_token
            export_dir.mkdir(parents=True, exist_ok=True)
            if request.kind == "workbook":
                wai_tables = (
                    _wai_tables(db, request.project_id, allowed_labs, encounters)
                    if _project_uses_remote_inference(db, request.project_id) else None
                )
                _write_workbook(
                    export_dir / "project_encounterset_export.xlsx", encounters, images, tasks,
                    wai_tables=wai_tables,
                )
                if request_data.get("sync_grant_uuid"):
                    _write_sync_duckdb(db, request.project_id, allowed_labs, grant_pii_labs, export_dir)
            else:
                _write_image_bundle(export_dir, encounters, images, tasks)
        db_set_job_status(job_token, "done")
        db_set_item_state(job_token, "project_export", "completed")
    except Exception as exc:
        db_set_job_status(job_token, "error", error=str(exc))
        db_set_item_state(job_token, "project_export", "error", str(exc))


def _write_sync_duckdb(db, project_id: int, labs, pii_labs, export_dir: Path) -> None:
    """Add the staged DuckDB package to a sync export, limited to the grant's labs and identifier rights.

    Skipped (workbook only) while the duckdb wheel is not installed, so the older export keeps working.
    """
    try:
        from project_export import ExportScope, export_package_for_scope
    except ImportError:
        return
    project = db.get(Project, project_id)
    try:
        export_package_for_scope(
            db, ExportScope(project_id, frozenset(labs), frozenset(pii_labs)), export_dir,
            stem=f"project_{project.code}", code=project.code, title=project.title,
        )
    except ImportError:  # duckdb itself missing: build_package imports it lazily
        return


def enqueue_project_export(app, job_token: str, request_data: dict[str, Any]) -> None:
    from utils.celery_helpers import celery_enabled, enqueue_task

    if celery_enabled():
        enqueue_task(
            "celery_tasks.tasks.export_tasks.run_project_export_task",
            job_token,
            request_data,
            user_id=request_data.get("actor_user_id"),
        )
        return
    app.config["EXECUTOR"].submit(_run_project_export, app, job_token, request_data)


def _run_project_export(app, job_token: str, request_data: dict[str, Any]) -> None:
    with app.app_context():
        run_project_export_job(job_token, request_data)


def project_export_preview(db, request: ProjectExportRequest, allowed_labs: frozenset[int]) -> dict[str, Any]:
    encounters = _encounters(db, request, allowed_labs)
    encounter_ids = [item.id for item in encounters]
    image_count = db.execute(
        select(func.count(EncounterSetImage.id)).where(
            EncounterSetImage.patient_encounter_id.in_(encounter_ids or [-1])
        )
    ).scalar_one()
    task_count = db.execute(
        select(func.count(GradingTask.id))
        .outerjoin(EncounterSetImage, EncounterSetImage.id == GradingTask.encounter_set_image_id)
        .where(or_(
            GradingTask.patient_encounter_id.in_(encounter_ids or [-1]),
            EncounterSetImage.patient_encounter_id.in_(encounter_ids or [-1]),
        ))
    ).scalar_one()
    return {
        "encounter_count": len(encounters),
        "image_count": int(image_count or 0),
        "task_count": int(task_count or 0),
        "image_export_limit": MAX_IMAGE_EXPORT_ENCOUNTERS,
        "image_export_allowed": len(encounters) <= MAX_IMAGE_EXPORT_ENCOUNTERS,
    }


def project_export_history(
    db, *, project_id: int, actor_user_id: int, limit: int = 10,
) -> tuple[ProjectExportHistoryItem, ...]:
    """Return the actor's recent project exports without exposing other users' jobs."""

    jobs = db.execute(
        select(Job)
        .where(
            Job.project_id == project_id,
            Job.uploader_user_id == actor_user_id,
            Job.upload_type == "project_export",
        )
        .order_by(Job.created_at.desc(), Job.id.desc())
        .limit(max(1, min(limit, 25)))
    ).scalars()
    history = []
    for job in jobs:
        export_dir = (EXPORT_DIR / job.token).resolve()
        files = ()
        if (
            job.status == "done"
            and EXPORT_DIR.resolve() in export_dir.parents
            and export_dir.is_dir()
        ):
            files = tuple(sorted(
                item.name for item in export_dir.iterdir()
                if item.is_file()
            ))
        history.append(ProjectExportHistoryItem(
            token=job.token,
            status=job.status,
            created_at=job.created_at,
            updated_at=job.updated_at,
            files=files,
        ))
    return tuple(history)


def _encounters(db, request: ProjectExportRequest, allowed_labs: frozenset[int]):
    task_encounter_id = func.coalesce(
        GradingTask.patient_encounter_id,
        select(EncounterSetImage.patient_encounter_id)
        .where(EncounterSetImage.id == GradingTask.encounter_set_image_id)
        .scalar_subquery(),
    )
    has_grade = exists().where(
        task_encounter_id == PatientEncounters.id,
        Grade.task_id == GradingTask.id,
    )
    has_task = exists().where(task_encounter_id == PatientEncounters.id)
    incomplete_task = exists().where(
        task_encounter_id == PatientEncounters.id,
        GradingTask.state != "final",
    )
    statement = select(PatientEncounters).where(
        PatientEncounters.project_id == request.project_id,
        PatientEncounters.is_set_based.is_(True),
        PatientEncounters.lab_unit_id.in_(allowed_labs),
    )
    if request.date_from:
        statement = statement.where(PatientEncounters.capture_date_dt >= request.date_from)
    if request.date_to:
        statement = statement.where(PatientEncounters.capture_date_dt <= request.date_to)
    if request.grading_filter == "any_graded":
        statement = statement.where(has_grade)
    elif request.grading_filter == "completed":
        statement = statement.where(has_task, ~incomplete_task)
    return list(
        db.execute(
            statement.options(
                selectinload(PatientEncounters.dr_reports),
                selectinload(PatientEncounters.amd_reports),
                selectinload(PatientEncounters.glaucoma_reports),
                selectinload(PatientEncounters.glaucoma_results_cleaned),
                selectinload(PatientEncounters.encounter_set_attachments),
            ).order_by(PatientEncounters.capture_date_dt, PatientEncounters.id)
        ).scalars()
    )


def _images(db, encounter_ids: list[int]):
    if not encounter_ids:
        return []
    return list(db.execute(
        select(EncounterSetImage)
        .where(EncounterSetImage.patient_encounter_id.in_(encounter_ids))
        .order_by(EncounterSetImage.patient_encounter_id, EncounterSetImage.spatial_position, EncounterSetImage.id)
    ).scalars())


def _tasks(db, encounter_ids: list[int]):
    if not encounter_ids:
        return []
    return list(db.execute(
        select(GradingTask)
        .outerjoin(EncounterSetImage, EncounterSetImage.id == GradingTask.encounter_set_image_id)
        .where(or_(
            GradingTask.patient_encounter_id.in_(encounter_ids),
            EncounterSetImage.patient_encounter_id.in_(encounter_ids),
        ))
        .options(
            selectinload(GradingTask.disease),
            selectinload(GradingTask.grades).selectinload(Grade.label),
            selectinload(GradingTask.consensus).selectinload(Consensus.final_label),
            selectinload(GradingTask.encounter_set_image),
            selectinload(GradingTask.encounter_set_package),
            selectinload(GradingTask.encounter_set_scope),
        )
        .order_by(GradingTask.id)
    ).unique().scalars())


def _project_uses_remote_inference(db, project_id: int) -> bool:
    """True when the project has any active remote-inference (WAI) configuration."""
    return any(
        db.execute(
            select(exists().where(model.project_id == project_id, model.active.is_(True)))
        ).scalar_one()
        for model in (
            ProjectEncounterAIWorkflow,
            ProjectAutomatedRemoteInferenceRule,
            ProjectManualRemoteInferenceWorkflow,
        )
    )


def _wai_tables(db, project_id: int, labs, encounters) -> dict[str, list[dict]]:
    """WAI sheets from the DuckDB package's remote_ai stage, so both exports read the same data.

    Scoped to the already-filtered encounters; no identifiers grant, so patient ids and file names
    are scrubbed exactly as they are in the package.
    """
    from project_export import ExportScope
    from project_export import stage_ai, tables

    scope = ExportScope(project_id, frozenset(labs))
    ctx = tables.BuildContext(db, scope, encounters, tables.collect_media(db, scope, encounters))
    return _wai_sheet_rows(stage_ai.build(ctx))


_WAI_BULKY = frozenset({"request_manifest", "response", "config_snapshot", "remote_key", "raw_output"})


def _wai_sheet_rows(ai: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """Encounter-level sheet (one row per run, DR/DME roll-up) and image-level sheet (one row per image x target).

    Raw provider payloads stay in the DuckDB package; they are too large for a worksheet.
    """
    targets_by_image: dict[tuple, list[dict]] = {}
    positives: dict[str, dict[str, Any]] = {}
    for target in ai["ai_target_results"]:
        targets_by_image.setdefault((target["run_id"], target["image_uuid"]), []).append(target)
        key = target["target_key"]
        entry = positives.setdefault(target["run_id"], {}).setdefault(key, {"positive": False, "grades": []})
        entry["positive"] = entry["positive"] or is_positive_output(key, target["mapped_grade"])
        if target["mapped_grade"] not in entry["grades"]:
            entry["grades"].append(target["mapped_grade"])
    image_counts: dict[str, int] = {}
    for image in ai["ai_image_results"]:
        image_counts[image["run_id"]] = image_counts.get(image["run_id"], 0) + 1

    encounter_rows = []
    for run in ai["ai_runs"]:
        if run["run_scope"] != "encounter":
            continue
        row = {k: _xlsx_value(v) for k, v in run.items() if k not in _WAI_BULKY and k not in ("task_uuid", "image_uuid", "prediction_id", "retry_count")}
        row["submitted_image_count"] = image_counts.get(run["run_id"], 0)
        for key, entry in sorted(positives.get(run["run_id"], {}).items()):
            row[f"{key}_positive"] = entry["positive"]
            row[f"{key}_grades"] = "; ".join(entry["grades"])
        encounter_rows.append(row)

    image_rows = []
    for image in ai["ai_image_results"]:
        base = {k: v for k, v in image.items() if k not in _WAI_BULKY}
        for target in targets_by_image.get((image["run_id"], image["image_uuid"])) or [{}]:
            image_rows.append({
                **base,
                **{k: _xlsx_value(target.get(k)) for k in ("target_key", "raw_label", "raw_score", "mapped_grade", "derivation_reason")},
            })
    # Single-image (task-level) runs have no per-image result rows; keep them visible rather than dropping them.
    for run in ai["ai_runs"]:
        if run["run_scope"] == "task":
            image_rows.append({
                "run_id": run["run_id"], "encounter_uuid": run["encounter_uuid"], "image_uuid": run["image_uuid"],
                "ai_model": run["ai_model"], "ai_model_version": run["ai_model_version"],
                "run_status": run["status"], "error_code": run["error_code"],
            })
    return {"WAI Encounter Results": encounter_rows, "WAI Image Results": image_rows}


def _export_filename(image: EncounterSetImage) -> str:
    source_name = image.edited_filename or image.original_filename
    return f"{image.uuid}{Path(source_name).suffix.lower() or '.jpg'}"


def _first_image_meta(image: Any, *keys: str) -> Any:
    meta = getattr(image, "metadata_json", None)
    if not isinstance(meta, dict):
        return None
    for key in keys:
        val = meta.get(key)
        if val not in (None, ""):
            return val
    return None


def _encounter_ocr_summary(encounter: Any) -> dict[str, Any]:
    dr_reports = sorted(getattr(encounter, "dr_reports", None) or [], key=lambda r: getattr(r, "id", 0) or 0)
    amd_reports = sorted(getattr(encounter, "amd_reports", None) or [], key=lambda r: getattr(r, "id", 0) or 0)
    gl_reports = sorted(getattr(encounter, "glaucoma_reports", None) or [], key=lambda r: getattr(r, "id", 0) or 0)
    gl_cleaned = sorted(
        getattr(encounter, "glaucoma_results_cleaned", None) or [],
        key=lambda r: getattr(r, "id", 0) or 0,
    )
    attachments = sorted(
        getattr(encounter, "encounter_set_attachments", None) or [],
        key=lambda r: getattr(r, "id", 0) or 0,
    )

    dr_latest = dr_reports[-1] if dr_reports else None
    amd_latest = amd_reports[-1] if amd_reports else None
    gl_latest = gl_reports[-1] if gl_reports else None
    gl_cleaned_latest = gl_cleaned[-1] if gl_cleaned else None

    dr_result = getattr(dr_latest, "result", None) if dr_latest else None
    dr_qual = getattr(dr_latest, "qualitative_result", None) if dr_latest else None
    amd_result = getattr(amd_latest, "result", None) if amd_latest else None
    amd_qual = getattr(amd_latest, "qualitative_result", None) if amd_latest else None
    gl_result = (
        getattr(gl_cleaned_latest, "result", None)
        if gl_cleaned_latest and getattr(gl_cleaned_latest, "result", None)
        else (getattr(gl_latest, "result", None) if gl_latest else None)
    )
    gl_qual = (
        getattr(gl_cleaned_latest, "qualitative_result", None)
        if gl_cleaned_latest and getattr(gl_cleaned_latest, "qualitative_result", None)
        else (getattr(gl_latest, "qualitative_result", None) if gl_latest else None)
    )
    gl_vcdr_right = (
        getattr(gl_latest, "vcdr_right", None)
        if gl_latest and getattr(gl_latest, "vcdr_right", None)
        else (getattr(gl_cleaned_latest, "original_vcdr_right", None) if gl_cleaned_latest else None)
    )
    gl_vcdr_left = (
        getattr(gl_latest, "vcdr_left", None)
        if gl_latest and getattr(gl_latest, "vcdr_left", None)
        else (getattr(gl_cleaned_latest, "original_vcdr_left", None) if gl_cleaned_latest else None)
    )
    gl_vcdr_right_num = getattr(gl_cleaned_latest, "vcdr_right_num", None) if gl_cleaned_latest else None
    gl_vcdr_left_num = getattr(gl_cleaned_latest, "vcdr_left_num", None) if gl_cleaned_latest else None

    remidio_ai_refer = None
    remidio_left_diag = None
    remidio_right_diag = None
    remidio_gma_refer = None
    remidio_gma_result = None
    remidio_gma_left_cdr = None
    remidio_gma_right_cdr = None

    for att in attachments:
        meta = getattr(att, "metadata_json", None)
        if not isinstance(meta, dict):
            continue
        if meta.get("ai_suggested_refer") is not None:
            remidio_ai_refer = meta.get("ai_suggested_refer")
        if meta.get("left_eye_diagnosis") not in (None, ""):
            remidio_left_diag = meta.get("left_eye_diagnosis")
        if meta.get("right_eye_diagnosis") not in (None, ""):
            remidio_right_diag = meta.get("right_eye_diagnosis")
        if meta.get("gma_suggested_refer") is not None:
            remidio_gma_refer = meta.get("gma_suggested_refer")
        if meta.get("gma_patient_level_result") not in (None, ""):
            remidio_gma_result = meta.get("gma_patient_level_result")
        if meta.get("gma_left_eye_cdr") is not None:
            remidio_gma_left_cdr = meta.get("gma_left_eye_cdr")
        if meta.get("gma_right_eye_cdr") is not None:
            remidio_gma_right_cdr = meta.get("gma_right_eye_cdr")

        ocr = meta.get("ocr") if isinstance(meta.get("ocr"), dict) else {}
        dr_ocr = ocr.get("dr_report") if isinstance(ocr.get("dr_report"), dict) else {}
        if dr_result is None and dr_ocr.get("result"):
            dr_result = dr_ocr.get("result")
        if dr_qual is None and dr_ocr.get("qualitative_result"):
            dr_qual = dr_ocr.get("qualitative_result")

        amd_ocr = ocr.get("amd_report") if isinstance(ocr.get("amd_report"), dict) else {}
        if amd_result is None and amd_ocr.get("result"):
            amd_result = amd_ocr.get("result")
        if amd_qual is None and amd_ocr.get("qualitative_result"):
            amd_qual = amd_ocr.get("qualitative_result")

        gl_ocr = ocr.get("glaucoma_report") if isinstance(ocr.get("glaucoma_report"), dict) else {}
        if gl_result is None and gl_ocr.get("result"):
            gl_result = gl_ocr.get("result")
        if gl_qual is None and gl_ocr.get("qualitative_result"):
            gl_qual = gl_ocr.get("qualitative_result")
        if gl_vcdr_right is None and gl_ocr.get("vcdr_right"):
            gl_vcdr_right = gl_ocr.get("vcdr_right")
        if gl_vcdr_left is None and gl_ocr.get("vcdr_left"):
            gl_vcdr_left = gl_ocr.get("vcdr_left")
        if gl_vcdr_right_num is None and gl_ocr.get("vcdr_right_num") is not None:
            gl_vcdr_right_num = gl_ocr.get("vcdr_right_num")
        if gl_vcdr_left_num is None and gl_ocr.get("vcdr_left_num") is not None:
            gl_vcdr_left_num = gl_ocr.get("vcdr_left_num")

    return {
        "referral_suggestion": getattr(encounter, "referral_suggestion", None),
        "referral_positive_diseases": _xlsx_value(getattr(encounter, "referral_positive_diseases_json", None)),
        "dr_ocr_result": dr_result,
        "dr_ocr_qualitative_result": dr_qual,
        "amd_ocr_result": amd_result,
        "amd_ocr_qualitative_result": amd_qual,
        "glaucoma_ocr_result": gl_result,
        "glaucoma_ocr_qualitative_result": gl_qual,
        "glaucoma_ocr_vcdr_right": gl_vcdr_right,
        "glaucoma_ocr_vcdr_left": gl_vcdr_left,
        "glaucoma_ocr_vcdr_right_num": gl_vcdr_right_num,
        "glaucoma_ocr_vcdr_left_num": gl_vcdr_left_num,
        "remidio_ai_suggested_refer": remidio_ai_refer,
        "remidio_left_eye_diagnosis": remidio_left_diag,
        "remidio_right_eye_diagnosis": remidio_right_diag,
        "remidio_gma_suggested_refer": remidio_gma_refer,
        "remidio_gma_patient_level_result": remidio_gma_result,
        "remidio_gma_left_eye_cdr": remidio_gma_left_cdr,
        "remidio_gma_right_eye_cdr": remidio_gma_right_cdr,
    }


def _write_workbook(path: Path, encounters, images, tasks, wai_tables=None) -> None:
    metadata_headers = collect_non_pii_metadata_headers(encounters)
    images_by_encounter = {}
    for image in images:
        images_by_encounter.setdefault(image.patient_encounter_id, []).append(image)
    tasks_by_encounter = {}
    for task in tasks:
        encounter_id = task.patient_encounter_id or task.encounter_set_image.patient_encounter_id
        tasks_by_encounter.setdefault(encounter_id, []).append(task)
    encounter_rows, image_rows, task_rows, grade_rows, final_rows = [], [], [], [], []
    for encounter in encounters:
        encounter_tasks = tasks_by_encounter.get(encounter.id, [])
        encounter_grades = [grade for task in encounter_tasks for grade in task.grades]
        encounter_row = {
            "encounter_uuid": encounter.uuid,
            "patient_id": encounter.patient_id,
            "capture_date": encounter.capture_date_dt or encounter.capture_date,
            "lab_unit_id": encounter.lab_unit_id,
            "verification_status": encounter.encounter_verified_status,
            "image_count": len(images_by_encounter.get(encounter.id, [])),
            "task_count": len(encounter_tasks),
            "grade_submission_count": len(encounter_grades),
            "final_task_count": sum(task.state == "final" for task in encounter_tasks),
            "all_tasks_complete": bool(encounter_tasks) and all(task.state == "final" for task in encounter_tasks),
        }
        encounter_row.update(_encounter_ocr_summary(encounter))
        metadata_values = non_pii_metadata_values(encounter.metadata_json)
        encounter_row.update({
            header: _xlsx_value(metadata_values.get(header, ""))
            for header in metadata_headers
        })
        encounter_rows.append(encounter_row)
    for image in images:
        gaze_position = _first_image_meta(image, "gaze_position", "strabismus_gaze_position", "gaze")
        centering = (
            _first_image_meta(image, "focus", "fundus_image_view", "fundus_field", "field", "image_segment", "centering")
            or gaze_position
        )
        image_rows.append({
            "encounter_uuid": next(item.uuid for item in encounters if item.id == image.patient_encounter_id),
            "image_uuid": image.uuid,
            "exported_filename": _export_filename(image),
            "spatial_position": image.spatial_position,
            "laterality": _first_image_meta(image, "laterality", "eye", "eye_side"),
            "centering": centering,
            "gaze_position": gaze_position,
            "visible_to_grader": image.visible_to_grader,
            "is_reviewed": image.is_reviewed,
            "is_not_gradable": image.is_not_gradable,
            "referral_needed_or_positive_image": getattr(image, "referral_needed_or_positive_image", None),
        })
    for task in tasks:
        encounter_id = task.patient_encounter_id or task.encounter_set_image.patient_encounter_id
        encounter_uuid = next(item.uuid for item in encounters if item.id == encounter_id)
        image_uuid = task.encounter_set_image.uuid if task.encounter_set_image else None
        task_rows.append({
            "encounter_uuid": encounter_uuid,
            "task_uuid": task.uuid,
            "image_uuid": image_uuid,
            "exported_filename": _export_filename(task.encounter_set_image) if task.encounter_set_image else None,
            "target_level": task.grading_target_level,
            "disease": task.disease.name,
            "state": task.state,
            "package": task.encounter_set_package.code if task.encounter_set_package else None,
            "scope_id": task.encounter_set_scope_id,
            "grade_submission_count": len(task.grades),
        })
        for grade in sorted(task.grades, key=lambda item: item.id):
            annotation_count = len(grade.feature_geometry_json.get("items", [])) if isinstance(grade.feature_geometry_json, dict) else 0
            grade_rows.append({
                "encounter_uuid": encounter_uuid,
                "task_uuid": task.uuid,
                "image_uuid": image_uuid,
                "exported_filename": _export_filename(task.encounter_set_image) if task.encounter_set_image else None,
                "disease": task.disease.name,
                "role_slot": grade.role_slot,
                "grade": grade.grade_name or grade.label.impression,
                "selected_features_json": grade.selected_features_json,
                "annotation_count": annotation_count,
                "submitted_at_utc": grade.updated_at.isoformat() if grade.updated_at else None,
                "time_taken_seconds": grade.time_taken,
            })
        final_rows.append({
            "encounter_uuid": encounter_uuid,
            "task_uuid": task.uuid,
            "image_uuid": image_uuid,
            "exported_filename": _export_filename(task.encounter_set_image) if task.encounter_set_image else None,
            "disease": task.disease.name,
            "task_state": task.state,
            "has_persisted_final_grade": task.consensus is not None,
            "final_grade": (
                task.consensus.final_grade_name
                or (
                    task.consensus.final_label.impression
                    if task.consensus.final_label else None
                )
            ) if task.consensus else None,
            "method": task.consensus.method if task.consensus else None,
            "consensus_scope": task.consensus.consensus_scope if task.consensus else None,
            "decided_at_utc": (
                task.consensus.decided_at.isoformat()
                if task.consensus and task.consensus.decided_at else None
            ),
        })
    sheets = [
        ("Encounters", encounter_rows), ("Images", image_rows), ("Tasks", task_rows),
        ("Grade Submissions", grade_rows), ("Final Grades", final_rows),
    ]
    if wai_tables is not None:
        sheets += list(wai_tables.items())
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for sheet, rows in sheets:
            pd.DataFrame(rows).to_excel(writer, sheet_name=sheet, index=False)


def _write_image_bundle(export_dir: Path, encounters, images, tasks) -> None:
    encounter_uuids = {item.id: item.uuid for item in encounters}
    image_payload = []
    for image in images:
        filename = image.edited_filename or image.original_filename
        candidate = (BASE_DIR / image.folder_rel / filename).resolve()
        image_payload.append({
            "task_id": None,
            "image_uuid": image.uuid,
            "image_filename": _export_filename(image),
            "image_path": candidate if candidate.is_relative_to(BASE_DIR.resolve()) else None,
            "encounter_uuid": encounter_uuids[image.patient_encounter_id],
            "image_s3_config_id": image.s3_config_id,
            "image_s3_object_key": image.s3_object_key_edited or image.s3_object_key,
        })
    task_rows = [{
        "task_id": task.id,
        "task_uuid": task.uuid,
        "image_uuid": task.encounter_set_image.uuid,
        "image_filename": _export_filename(task.encounter_set_image),
        "disease": task.disease.name,
        "final_impression": (
            task.consensus.final_grade_name
            or (
                task.consensus.final_label.impression
                if task.consensus.final_label else None
            )
        ) if task.consensus else None,
    } for task in tasks if task.encounter_set_image is not None]
    manifest = write_annotation_export(task_rows, export_dir / "annotations.json")
    exported_images = {}
    _zip_paths, warnings = _write_zips(
        image_payload, export_dir, annotation_manifest=manifest,
        exported_images=exported_images,
    )
    warnings.extend(write_coco_exports(manifest, exported_images, export_dir))
    write_annotator_exports(manifest, exported_images, export_dir)
    if warnings:
        (export_dir / "warnings.txt").write_text("\n".join(warnings), encoding="utf-8")
