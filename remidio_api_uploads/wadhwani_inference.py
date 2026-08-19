from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from auth.roles import roles_required
from db_transaction_manager import get_db_session, transaction_scope
from encounter_sets.models import EncounterSetAttachment
from models import AIInferenceRun, Camera, EncounterSetImage, Grade, GradingTask, Job, JobItem, PatientEncounters
from remote_inference.manual_service import list_manual_wadhwani_projects, project_allows_manual_wadhwani
from remote_inference import encounter_service
from remote_inference.dr_dme import ALLOWED_PAGE_SIZES, CandidateFilters as DrDmeCandidateFilters
from remote_inference.dr_dme import MAX_MANUAL_ENCOUNTERS as MAX_DR_DME_ENCOUNTERS
from remote_inference.dr_dme import list_candidates as list_dr_dme_candidates
from remote_inference.job_service import is_job_resumable
from services.encounter_set_ai_inference import enqueue_wadhwani_for_task_ids
from utils.hospital_scoping import apply_scoping
from utils.wadhwani_glaucoma_selector import get_glaucoma_disease, get_linked_wadhwani_integration

from . import bp


WADHWANI_ENCOUNTER_SET_JOB_TYPE = "encounter_set_wadhwani_inference"
WADHWANI_RETRY_JOB_TYPE = "wai_api_statistics_retry"
AI_PROBABILITY_PATTERN = re.compile(r"AI probability:\s*([0-9.]+)", flags=re.IGNORECASE)
PAGE_ROLES = ("admin", "local_admin", "data_manager")
ENCOUNTER_SETS_PER_PAGE = 25
MAX_ENCOUNTER_SETS_PER_BATCH = 25


@dataclass(frozen=True)
class InferenceFilters:
    project_id: int | None
    capture_date_from: str
    capture_date_to: str
    camera_id: str
    laterality: str
    focus: str
    glaucoma_report: str
    include_prior: bool
    page: int


@bp.route("/uploads/encountersets/wadhwani_inference", methods=["GET"])
@roles_required(*PAGE_ROLES)
def encounter_set_wadhwani_inference():
    if request.args.get("workflow") == "dr_dme":
        return _madhunetra_page(include_encounters=False)
    filters = _filters_from_request(request.args)
    with get_db_session() as db:
        integration = get_linked_wadhwani_integration(db)
        projects = _configured_projects(db)
        cameras = _cameras(db)
        context = _page_context(db, filters, integration, projects, cameras, include_encounters=False)
    return render_template("remidio_api_uploads/wadhwani_inference.html", **context)


@bp.route("/uploads/encountersets/wadhwani_inference/workspace", methods=["GET"])
@roles_required(*PAGE_ROLES)
def encounter_set_wadhwani_inference_workspace():
    if request.args.get("workflow") == "dr_dme":
        return _madhunetra_page(include_encounters=True, partial=True)
    filters = _filters_from_request(request.args)
    with get_db_session() as db:
        integration = get_linked_wadhwani_integration(db)
        projects = _configured_projects(db)
        cameras = _cameras(db)
        context = _page_context(db, filters, integration, projects, cameras, include_encounters=True)
    return render_template("remidio_api_uploads/_wadhwani_inference_workspace.html", **context)


@bp.route("/uploads/encountersets/wadhwani_inference/run", methods=["POST"])
@roles_required(*PAGE_ROLES)
def encounter_set_wadhwani_inference_run():
    if request.form.get("workflow") == "dr_dme":
        project_id = _optional_int(request.form.get("project_id"))
        encounter_ids = [value for value in (_optional_int(raw) for raw in request.form.getlist("selected_encounter_ids")) if value]
        if not project_id:
            flash("Select a project before queueing DR-DME screening.", "warning")
            return redirect(url_for("remidio_api_uploads.encounter_set_wadhwani_inference", workflow="dr_dme"))
        xff = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
        result = encounter_service.create_manual_job(
            encounter_ids=encounter_ids,
            project_id=project_id,
            user=current_user,
            remote_addr=xff or (request.remote_addr or "-"),
        )
        if not result.success:
            flash(result.message, "warning" if result.status_code < 500 else "danger")
            return redirect(url_for("remidio_api_uploads.encounter_set_wadhwani_inference", workflow="dr_dme", project_id=project_id))
        return redirect(url_for("remidio_api_uploads.encounter_set_wadhwani_inference_job", job_token=result.payload["job_token"], workflow="dr_dme"))
    project_id = _optional_int(request.form.get("project_id"))
    image_ids = _selected_image_ids_from_request()
    if not project_id:
        flash("Select a project before queueing Wadhwani inference.", "warning")
        return redirect(url_for("remidio_api_uploads.encounter_set_wadhwani_inference"))
    if not image_ids:
        flash("Select at least one EncounterSet image.", "warning")
        return redirect(url_for("remidio_api_uploads.encounter_set_wadhwani_inference", project_id=project_id))

    xff = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
    remote_addr = xff or (request.remote_addr or "-")
    with transaction_scope() as db:
        integration = get_linked_wadhwani_integration(db)
        glaucoma = get_glaucoma_disease(db)
        if integration is None or glaucoma is None:
            flash("No linked Wadhwani glaucoma model is configured.", "danger")
            return redirect(url_for("remidio_api_uploads.encounter_set_wadhwani_inference", project_id=project_id))
        if not project_allows_manual_wadhwani(db, project_id):
            flash("Manual Wadhwani glaucoma inference is not enabled for the selected project.", "warning")
            return redirect(url_for("remidio_api_uploads.encounter_set_wadhwani_inference", project_id=project_id))
        selected_encounter_count = _selected_encounter_count(db, project_id=project_id, image_ids=image_ids)
        if selected_encounter_count > MAX_ENCOUNTER_SETS_PER_BATCH:
            flash(f"Select at most {MAX_ENCOUNTER_SETS_PER_BATCH} EncounterSets per batch.", "warning")
            return redirect(url_for("remidio_api_uploads.encounter_set_wadhwani_inference", project_id=project_id))
        task_ids = _create_or_reuse_image_tasks(db, project_id=project_id, image_ids=image_ids, disease_id=glaucoma.id)
        if not task_ids:
            flash("No selected images are eligible for Wadhwani inference.", "warning")
            return redirect(url_for("remidio_api_uploads.encounter_set_wadhwani_inference", project_id=project_id))
        db.flush()

    job_token = enqueue_wadhwani_for_task_ids(
        task_ids,
        user_id=current_user.id,
        username=getattr(current_user, "username", None),
        remote_addr=remote_addr,
        lab_unit_id=None,
        project_id=project_id,
        upload_profile_id=None,
    )
    if not job_token:
        flash("No selected tasks remain queueable for Wadhwani inference.", "warning")
        return redirect(url_for("remidio_api_uploads.encounter_set_wadhwani_inference", project_id=project_id))
    return redirect(url_for("remidio_api_uploads.encounter_set_wadhwani_inference_job", job_token=job_token))


@bp.route("/uploads/encountersets/wadhwani_inference/jobs/<job_token>", methods=["GET"])
@roles_required(*PAGE_ROLES)
def encounter_set_wadhwani_inference_job(job_token: str):
    workflow = request.args.get("workflow", "glaucoma")
    return render_template(
        "remidio_api_uploads/wadhwani_inference_job.html",
        job_token=job_token,
        page_title="Encounter DR-DME Screening Status" if workflow == "dr_dme" else "EncounterSet Wadhwani Inference Status",
        workflow=workflow,
    )


@bp.route("/uploads/encountersets/wadhwani_inference/jobs/<job_token>/status", methods=["GET"])
@roles_required(*PAGE_ROLES)
def encounter_set_wadhwani_inference_job_status(job_token: str):
    with get_db_session() as db:
        if request.args.get("workflow") == "dr_dme":
            payload = encounter_service.load_job_payload(db, job_token)
            if payload is None:
                abort(404)
            return (
                render_template("remidio_api_uploads/_madhunetra_job_status.html", job=payload),
                286 if payload["done"] else 200,
            )
        payload = _load_job_payload(db, job_token)
        if payload is None:
            abort(404)
    return (
        render_template("remidio_api_uploads/_wadhwani_inference_job_status.html", job=payload),
        286 if payload["done"] else 200,
    )


def _madhunetra_page(*, include_encounters: bool, partial: bool = False):
    project_id = _optional_int(request.args.get("project_id"))
    with get_db_session() as db:
        projects = encounter_service.list_manual_projects(db, current_user)
        if project_id is None or not any(row["id"] == project_id for row in projects):
            project_id = projects[0]["id"] if projects else None
        integration = encounter_service.integration_context(db)
        cameras = _cameras(db)
        filters = _dr_dme_filters_from_request(project_id)
        candidate_page = (
            list_dr_dme_candidates(db, filters=filters, user=current_user)
            if include_encounters and project_id else None
        )
    context = {
        "page_title": "Encounter DR-DME Screening",
        "workflow": "dr_dme",
        "projects": projects,
        "project_id": project_id,
        "linked_integration": integration if integration and integration["is_enabled"] else None,
        "filters": filters,
        "cameras": cameras,
        "encounters": candidate_page.rows if candidate_page else (),
        "pagination": candidate_page,
        "filter_stats": {
            "encounter_count": candidate_page.encounter_count if candidate_page else 0,
            "image_count": candidate_page.image_count if candidate_page else 0,
        },
        "allowed_page_sizes": ALLOWED_PAGE_SIZES,
        "max_encounter_sets_per_batch": MAX_DR_DME_ENCOUNTERS,
    }
    template = "remidio_api_uploads/_madhunetra_workspace.html" if partial else "remidio_api_uploads/madhunetra_inference.html"
    return render_template(template, **context)


def _dr_dme_filters_from_request(project_id: int | None) -> DrDmeCandidateFilters:
    return DrDmeCandidateFilters(
        project_id=project_id or 0,
        capture_date_from=str(request.args.get("capture_date_from") or ""),
        capture_date_to=str(request.args.get("capture_date_to") or ""),
        camera_id=str(request.args.get("camera_id") or ""),
        dr_report=str(request.args.get("dr_report") or ""),
        include_prior=request.args.get("include_prior") in {"1", "true", "on", "yes"},
        page=_optional_int(request.args.get("page")) or 1,
        page_size=_optional_int(request.args.get("page_size")) or ALLOWED_PAGE_SIZES[0],
    ).normalized()


def _page_context(
    db,
    filters: InferenceFilters,
    integration,
    projects: list[dict],
    cameras: list[dict],
    *,
    include_encounters: bool,
) -> dict[str, Any]:
    selected_project_id = filters.project_id or (projects[0]["id"] if projects else None)
    if selected_project_id and not any(project["id"] == selected_project_id for project in projects):
        selected_project_id = projects[0]["id"] if projects else None
    filters = InferenceFilters(
        project_id=selected_project_id,
        capture_date_from=filters.capture_date_from,
        capture_date_to=filters.capture_date_to,
        camera_id=filters.camera_id,
        laterality=filters.laterality,
        focus=filters.focus,
        glaucoma_report=filters.glaucoma_report,
        include_prior=filters.include_prior,
        page=filters.page,
    )
    glaucoma = get_glaucoma_disease(db) if include_encounters else None
    encounters = (
        _encounter_cards(
            db,
            filters,
            integration.ai_model_id if integration else None,
            glaucoma.id if glaucoma else None,
        )
        if include_encounters
        else None
    )
    return {
        "page_title": "EncounterSet Wadhwani Inference",
        "linked_integration": integration,
        "projects": projects,
        "cameras": cameras,
        "filters": filters,
        "encounters": encounters["rows"] if encounters else [],
        "pagination": encounters["pagination"] if encounters else {"page": filters.page, "has_prev": False, "has_next": False},
        "filter_stats": encounters["stats"] if encounters else {"encounter_count": 0, "image_count": 0},
        "max_encounter_sets_per_batch": MAX_ENCOUNTER_SETS_PER_BATCH,
    }


def _configured_projects(db) -> list[dict[str, Any]]:
    return list_manual_wadhwani_projects(db, current_user)


def _cameras(db) -> list[dict[str, Any]]:
    return [{"id": camera.id, "name": camera.name} for camera in db.execute(select(Camera).order_by(Camera.name)).scalars().all()]


def _encounter_cards(
    db,
    filters: InferenceFilters,
    ai_model_id: int | None,
    glaucoma_disease_id: int | None,
) -> dict[str, Any]:
    if not filters.project_id:
        return {
            "rows": [],
            "pagination": {"page": max(filters.page, 1), "has_prev": False, "has_next": False, "prev_page": 1, "next_page": 1, "page_size": ENCOUNTER_SETS_PER_PAGE},
            "stats": {"encounter_count": 0, "image_count": 0},
        }
    query = (
        db.query(PatientEncounters)
        .options(
            selectinload(PatientEncounters.lab_unit),
            selectinload(PatientEncounters.encounter_set_images).selectinload(EncounterSetImage.camera),
            selectinload(PatientEncounters.encounter_set_attachments),
        )
        .filter(PatientEncounters.is_set_based.is_(True), PatientEncounters.project_id == filters.project_id)
        .order_by(PatientEncounters.capture_date_dt.desc().nullslast(), PatientEncounters.id.desc())
    )
    if filters.capture_date_from:
        date_from = _date_value(filters.capture_date_from)
        if date_from:
            query = query.filter(PatientEncounters.capture_date_dt >= date_from)
    if filters.capture_date_to:
        date_to = _date_value(filters.capture_date_to)
        if date_to:
            query = query.filter(PatientEncounters.capture_date_dt <= date_to)
    query = apply_scoping(query, PatientEncounters, current_user, "upload")

    image_rows: list[Any] = []
    matched_rows: list[dict[str, Any]] = []
    page_size = ENCOUNTER_SETS_PER_PAGE
    page = max(filters.page, 1)
    for encounter in query.all():
        images = []
        ocr_summary = _glaucoma_ocr_summary(encounter.encounter_set_attachments or [])
        if filters.glaucoma_report == "present" and not ocr_summary:
            continue
        if filters.glaucoma_report == "absent" and ocr_summary:
            continue
        for image in sorted(encounter.encounter_set_images or [], key=lambda item: (item.spatial_position, item.id)):
            if not _image_matches_filters(image, filters):
                continue
            images.append(image)
            image_rows.append(image)
        if images:
            matched_rows.append({"encounter": encounter, "ocr": ocr_summary, "images": images})

    status_by_image_id = (
        _wadhwani_status_by_image(db, image_rows, ai_model_id, glaucoma_disease_id)
        if image_rows and ai_model_id and glaucoma_disease_id
        else {}
    )
    cards: list[dict[str, Any]] = []
    total_image_count = 0
    for row in matched_rows:
        image_cards = []
        for image in row["images"]:
            status = status_by_image_id.get(image.id, _empty_status())
            if not filters.include_prior and status["has_prior"]:
                continue
            image_cards.append(_image_card(image, status))
        if image_cards:
            total_image_count += len(image_cards)
            cards.append(
                {
                    "id": row["encounter"].id,
                    "uuid": row["encounter"].uuid,
                    "capture_date": row["encounter"].capture_date_dt or row["encounter"].capture_date,
                    "patient_id": row["encounter"].patient_id,
                    "lab_unit_name": row["encounter"].lab_unit.name if row["encounter"].lab_unit else None,
                    "ocr": row["ocr"],
                    "images": image_cards,
                }
            )
    total_encounter_count = len(cards)
    start = (page - 1) * page_size
    page_cards = cards[start : start + page_size]
    has_next = start + page_size < total_encounter_count
    return {
        "rows": page_cards,
        "pagination": {
            "page": page,
            "has_prev": page > 1,
            "has_next": has_next,
            "prev_page": page - 1,
            "next_page": page + 1,
            "page_size": page_size,
        },
        "stats": {
            "encounter_count": total_encounter_count,
            "image_count": total_image_count,
        },
    }


def _image_matches_filters(image, filters: InferenceFilters) -> bool:
    metadata = image.metadata_json or {}
    if image.asset_kind != "clinical_image" or not image.creates_task or not image.visible_to_grader or image.is_not_gradable:
        return False
    if filters.camera_id and str(image.camera_id or "") != filters.camera_id:
        return False
    if filters.laterality and _norm(metadata.get("laterality")) != filters.laterality:
        return False
    if filters.focus and _norm(metadata.get("focus") or metadata.get("fundus_field") or metadata.get("image_segment")) != filters.focus:
        return False
    return True


def _wadhwani_status_by_image(
    db,
    images: list[Any],
    ai_model_id: int,
    glaucoma_disease_id: int,
) -> dict[int, dict[str, Any]]:
    image_ids = [image.id for image in images]
    tasks = db.execute(
        select(GradingTask).where(
            GradingTask.encounter_set_image_id.in_(image_ids),
            GradingTask.disease_id == glaucoma_disease_id,
        )
    ).scalars().all()
    tasks_by_image_id: dict[int, list[GradingTask]] = {}
    for task in tasks:
        tasks_by_image_id.setdefault(task.encounter_set_image_id, []).append(task)
    task_ids = [task.id for task in tasks]
    latest_runs: dict[int, AIInferenceRun] = {}
    if task_ids:
        runs = db.execute(
            select(AIInferenceRun)
            .where(AIInferenceRun.task_id.in_(task_ids), AIInferenceRun.ai_model_id == ai_model_id)
            .order_by(AIInferenceRun.created_at.desc(), AIInferenceRun.id.desc())
        ).scalars().all()
        for run in runs:
            latest_runs.setdefault(run.task_id, run)
    grades = {}
    if task_ids:
        grade_rows = db.execute(
            select(Grade)
            .where(Grade.task_id.in_(task_ids), Grade.role_slot == "ai", Grade.ai_model_id == ai_model_id)
            .order_by(Grade.created_at.desc(), Grade.id.desc())
        ).scalars().all()
        for grade in grade_rows:
            grades.setdefault(grade.task_id, grade)
    status_by_image_id = {}
    for image_id in image_ids:
        image_tasks = tasks_by_image_id.get(image_id, [])
        task_with_prior = next(
            (
                task
                for task in sorted(image_tasks, key=lambda row: row.id, reverse=True)
                if task.id in latest_runs or task.id in grades
            ),
            None,
        )
        fallback_task = min(image_tasks, key=lambda row: row.id) if image_tasks else None
        status_by_image_id[image_id] = _status_payload(
            task_with_prior or fallback_task,
            latest_runs,
            grades,
        )
    return status_by_image_id


def _status_payload(task, latest_runs: dict[int, AIInferenceRun], grades: dict[int, Grade]) -> dict[str, Any]:
    if task is None:
        return _empty_status()
    run = latest_runs.get(task.id)
    grade = grades.get(task.id)
    if run is None and grade is None:
        payload = _empty_status()
        payload["task_id"] = task.id
        return payload
    result_row = _result_row(run)
    state = "success" if grade or (run and run.status == "success") else "failed" if run and run.status == "failed" else "running" if run and run.status == "running" else "pending"
    return {
        "task_id": task.id,
        "run_id": run.id if run else None,
        "run_status": run.status if run else None,
        "state": state,
        "grade_name": grade.grade_name if grade else None,
        "probability": _grade_probability(grade),
        "prediction": result_row.get("prediction"),
        "predicted_class_name": result_row.get("predicted_class_name"),
        "model_score": result_row.get("model_score"),
        "confidence": result_row.get("confidence"),
        "has_prior": bool(run or grade),
        "updated_at": (run.finished_at or run.updated_at) if run else (grade.updated_at if grade else None),
    }


def _image_card(image, status: dict[str, Any]) -> dict[str, Any]:
    metadata = image.metadata_json or {}
    return {
        "id": image.id,
        "uuid": image.uuid,
        "position": image.spatial_position,
        "filename": image.edited_filename or image.original_filename,
        "camera_name": image.camera.name if image.camera else None,
        "laterality": metadata.get("laterality"),
        "focus": metadata.get("focus") or metadata.get("fundus_field") or metadata.get("image_segment"),
        "variant": metadata.get("image_variant"),
        "quality": metadata.get("remidio_image_quality"),
        "status": status,
    }


def _glaucoma_ocr_summary(attachments: list[EncounterSetAttachment]) -> dict[str, Any] | None:
    for attachment in attachments:
        metadata = attachment.metadata_json or {}
        ocr = metadata.get("ocr") if isinstance(metadata.get("ocr"), dict) else {}
        report = ocr.get("glaucoma_report") if isinstance(ocr.get("glaucoma_report"), dict) else None
        if not report:
            continue
        data = report.get("glaucoma_data") if isinstance(report.get("glaucoma_data"), dict) else {}
        return {
            "status": ocr.get("status"),
            "result": data.get("result"),
            "qualitative_result": data.get("qualitative_result"),
            "vcdr_right": data.get("vcdr_right"),
            "vcdr_left": data.get("vcdr_left"),
            "page": report.get("page"),
            "attachment_filename": attachment.original_filename,
        }
    return None


def _create_or_reuse_image_tasks(db, *, project_id: int, image_ids: list[int], disease_id: int) -> list[int]:
    scoped = (
        db.query(PatientEncounters)
        .join(PatientEncounters.encounter_set_images)
        .filter(PatientEncounters.project_id == project_id)
    )
    scoped = apply_scoping(scoped, PatientEncounters, current_user, "upload")
    allowed_encounter_ids = {row.id for row in scoped.all()}

    selected_images = (
        db.query(EncounterSetImage)
        .filter(
            EncounterSetImage.id.in_(image_ids),
            EncounterSetImage.patient_encounter_id.in_(allowed_encounter_ids),
            EncounterSetImage.asset_kind == "clinical_image",
            EncounterSetImage.creates_task.is_(True),
            EncounterSetImage.visible_to_grader.is_(True),
            EncounterSetImage.is_not_gradable.is_(False),
        )
        .all()
    )
    task_ids: list[int] = []
    for image in selected_images:
        encounter = db.get(PatientEncounters, image.patient_encounter_id)
        if encounter is None or not encounter.lab_unit_id:
            continue
        task = (
            db.query(GradingTask)
            .filter(GradingTask.encounter_set_image_id == image.id, GradingTask.disease_id == disease_id)
            .first()
        )
        if task is None:
            task = GradingTask(
                encounter_set_image_id=image.id,
                disease_id=disease_id,
                lab_unit_id=encounter.lab_unit_id,
                source_upload_profile_id=encounter.upload_profile_id,
                grading_target_level="image",
                task_source="encounter_set_ai_inference",
            )
            db.add(task)
            db.flush()
        task_ids.append(task.id)
    return task_ids


def _selected_encounter_count(db, *, project_id: int, image_ids: list[int]) -> int:
    scoped = (
        db.query(PatientEncounters.id)
        .join(PatientEncounters.encounter_set_images)
        .filter(PatientEncounters.project_id == project_id, EncounterSetImage.id.in_(image_ids))
        .distinct()
    )
    scoped = apply_scoping(scoped, PatientEncounters, current_user, "upload")
    return scoped.count()


def _load_job_payload(db, job_token: str) -> dict[str, Any] | None:
    job = db.execute(
        select(Job).where(
            Job.token == job_token,
            Job.upload_type.in_((WADHWANI_ENCOUNTER_SET_JOB_TYPE, WADHWANI_RETRY_JOB_TYPE)),
        )
    ).scalar_one_or_none()
    if job is None:
        return None
    items = db.execute(select(JobItem).where(JobItem.job_id == job.id).order_by(JobItem.id)).scalars().all()
    task_ids = [_task_id_from_item(item) for item in items]
    task_ids = [task_id for task_id in task_ids if task_id]
    tasks = db.execute(
        select(GradingTask)
        .options(
            selectinload(GradingTask.encounter_set_image).selectinload(EncounterSetImage.camera),
            selectinload(GradingTask.encounter_set_image).selectinload(EncounterSetImage.patient_encounter),
        )
        .where(GradingTask.id.in_(task_ids))
    ).scalars().all() if task_ids else []
    task_by_id = {task.id: task for task in tasks}
    grade_ids: list[int] = []
    inference_run_ids: list[int] = []
    parsed_by_item_id: dict[int, dict[str, Any]] = {}
    for item in items:
        parsed = _json_detail(item.detail)
        parsed_by_item_id[item.id] = parsed
        if isinstance(parsed.get("grade_id"), int):
            grade_ids.append(parsed["grade_id"])
        if isinstance(parsed.get("inference_run_id"), int):
            inference_run_ids.append(parsed["inference_run_id"])
    grades_by_id = {
        grade.id: grade
        for grade in db.execute(select(Grade).where(Grade.id.in_(grade_ids))).scalars().all()
    } if grade_ids else {}
    runs_by_id = {
        run.id: run
        for run in db.execute(select(AIInferenceRun).where(AIInferenceRun.id.in_(inference_run_ids))).scalars().all()
    } if inference_run_ids else {}
    groups_by_key: dict[str, dict[str, Any]] = {}
    summary = {"queued": 0, "processing": 0, "ok": 0, "error": 0, "positive": 0}
    for item in items:
        state = (item.state or "queued").lower()
        summary[state if state in summary else "queued"] += 1
        parsed = parsed_by_item_id.get(item.id, {})
        task_id = _task_id_from_item(item)
        task = task_by_id.get(task_id) if task_id else None
        image = task.encounter_set_image if task else None
        grade = grades_by_id.get(parsed.get("grade_id")) if isinstance(parsed.get("grade_id"), int) else None
        run = runs_by_id.get(parsed.get("inference_run_id")) if isinstance(parsed.get("inference_run_id"), int) else None
        result_row = _result_row(run)
        if _is_positive_wadhwani_result(grade, result_row):
            summary["positive"] += 1
        encounter = image.patient_encounter if image else None
        group_key = encounter.uuid if encounter else "unknown"
        group = groups_by_key.setdefault(
            group_key,
            {
                "encounter_id": encounter.id if encounter else None,
                "encounter_uuid": encounter.uuid if encounter else None,
                "patient_id": encounter.patient_id if encounter else None,
                "capture_date": encounter.capture_date_dt or encounter.capture_date if encounter else None,
                "items": [],
            },
        )
        group["items"].append(
            {
                "task_id": task_id,
                "state": state,
                "message": parsed.get("message"),
                "grade_id": parsed.get("grade_id"),
                "inference_run_id": parsed.get("inference_run_id"),
                "error_code": parsed.get("error_code"),
                "grade_name": grade.grade_name if grade else None,
                "probability": _grade_probability(grade),
                "prediction": result_row.get("prediction"),
                "predicted_class_name": result_row.get("predicted_class_name"),
                "predicted_class": result_row.get("predicted_class"),
                "model_score": result_row.get("model_score"),
                "confidence": result_row.get("confidence"),
                "image": _image_card(image, _empty_status()) if image else None,
            }
        )
    groups = list(groups_by_key.values())
    groups.sort(key=lambda group: (str(group.get("capture_date") or ""), str(group.get("encounter_uuid") or "")))
    return {
        "token": job.token,
        "status": job.status,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "groups": groups,
        "summary": summary,
        "done": str(job.status or "").lower() in {"done", "error", "partial"},
        "resumable": is_job_resumable(job, items),
    }


def _filters_from_request(args) -> InferenceFilters:
    return InferenceFilters(
        project_id=_optional_int(args.get("project_id")),
        capture_date_from=args.get("capture_date_from", ""),
        capture_date_to=args.get("capture_date_to", ""),
        camera_id=args.get("camera_id", ""),
        laterality=_norm(args.get("laterality")),
        focus=_norm(args.get("focus")),
        glaucoma_report=args.get("glaucoma_report", ""),
        include_prior=args.get("include_prior") == "1",
        page=max(1, _optional_int(args.get("page")) or 1),
    )


def _selected_image_ids_from_request() -> list[int]:
    values = []
    for raw in request.form.getlist("selected_image_ids"):
        value = _optional_int(raw)
        if value:
            values.append(value)
    return list(dict.fromkeys(values))


def _empty_status() -> dict[str, Any]:
    return {"has_prior": False, "state": "not_requested"}


def _result_row(run: AIInferenceRun | None) -> dict[str, Any]:
    if not run or not run.execute_response_json:
        return {}
    rows = run.execute_response_json.get("results") or []
    return rows[0] or {} if rows else {}


def _is_positive_wadhwani_result(grade: Grade | None, result_row: dict[str, Any]) -> bool:
    prediction = str(result_row.get("prediction") or "").strip().lower()
    predicted_class = result_row.get("predicted_class")
    if prediction == "referrable" or predicted_class == 1 or str(predicted_class) == "1":
        return True
    return str(grade.grade_name or "").strip().lower() == "glaucoma" if grade else False


def _grade_probability(grade: Grade | None) -> str | None:
    if not grade or not grade.comment:
        return None
    match = AI_PROBABILITY_PATTERN.search(grade.comment)
    return match.group(1) if match else None


def _task_id_from_item(item: JobItem) -> int | None:
    if not item.filename.startswith("task:"):
        return None
    return _optional_int(item.filename.split(":", 1)[1])


def _json_detail(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {"message": value}
    except json.JSONDecodeError:
        return {"message": value}


def _optional_int(value: str | None) -> int | None:
    if value in {None, ""}:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _date_value(value: str):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()
