from __future__ import annotations

import json
import re

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from auth.roles import roles_required
from db_transaction_manager import get_db_session
from job_store import db_create_job
from models import Camera, Hospital, Job, JobItem, LabUnit
from utils.celery_helpers import enqueue_task
from authz.behaviors import clinical_lab_units
from utils.wadhwani_glaucoma_selector import (
    DEFAULT_MANUAL_WADHWANI_LIMIT,
    MAX_MANUAL_WADHWANI_BATCH,
    filter_still_eligible_task_ids,
    get_glaucoma_grade_options,
    get_linked_wadhwani_integration,
    list_eligible_wadhwani_glaucoma_tasks,
    list_zip_glaucoma_result_options,
)

WADHWANI_JOB_TYPE = "wadhwani_glaucoma_inference"
AI_PROBABILITY_PATTERN = re.compile(r"AI probability:\s*([0-9.]+)", flags=re.IGNORECASE)


def register_routes(bp):
    bp.add_url_rule(
        "/wadhwani-glaucoma-inference/",
        view_func=wadhwani_glaucoma_inference_page,
        methods=["GET"],
    )
    bp.add_url_rule(
        "/wadhwani-glaucoma-inference/run",
        view_func=wadhwani_glaucoma_inference_run,
        methods=["POST"],
    )
    bp.add_url_rule(
        "/wadhwani-glaucoma-inference/jobs/<job_token>",
        view_func=wadhwani_glaucoma_inference_job_page,
        methods=["GET"],
    )
    bp.add_url_rule(
        "/wadhwani-glaucoma-inference/jobs/<job_token>/status",
        view_func=wadhwani_glaucoma_inference_job_status_partial,
        methods=["GET"],
    )


@roles_required("admin", "local_admin", "data_manager")
def wadhwani_glaucoma_inference_page():
    with get_db_session() as db:
        integration = get_linked_wadhwani_integration(db)
        linked_model_id = integration.ai_model_id if integration else None
        scoped_lab_units = _allowed_lab_units(db)
        allowed_lab_unit_ids = [lab.id for lab in scoped_lab_units]
        lab_units = [
            {
                "id": lab.id,
                "name": lab.name,
                "hospital_name": lab.hospital.name if getattr(lab, "hospital", None) else "",
            }
            for lab in scoped_lab_units
        ]
        cameras = [
            {"id": camera.id, "name": camera.name}
            for camera in db.execute(select(Camera).order_by(Camera.name)).scalars().all()
        ]
        hospitals = [
            {"id": hospital.id, "name": hospital.name}
            for hospital in db.execute(select(Hospital).order_by(Hospital.name)).scalars().all()
        ]
        final_grade_options = get_glaucoma_grade_options(db)
        zip_result_options = list_zip_glaucoma_result_options(db)
        filters = _filters_from_request(request.args)
        tasks = []
        if integration and filters["source_type"] in {"zip", "direct", "pregraded"}:
            tasks = list_eligible_wadhwani_glaucoma_tasks(
                db,
                ai_model_id=integration.ai_model_id,
                allowed_lab_unit_ids=allowed_lab_unit_ids,
                filters=filters,
            )

    context = {
        "page_title": "Wadhwani Glaucoma Inference",
        "linked_integration": integration,
        "linked_model_id": linked_model_id,
        "lab_units": lab_units,
        "cameras": cameras,
        "hospitals": hospitals,
        "final_grade_options": final_grade_options,
        "zip_result_options": zip_result_options,
        "filters": filters,
        "tasks": tasks,
        "max_batch_size": MAX_MANUAL_WADHWANI_BATCH,
    }
    if request.headers.get("HX-Request") == "true":
        return render_template("grading/_wadhwani_glaucoma_results.html", **context)
    return render_template("grading/wadhwani_glaucoma_inference.html", **context)


@roles_required("admin", "local_admin", "data_manager")
def wadhwani_glaucoma_inference_run():
    selected_task_ids = _selected_task_ids_from_request()
    if not selected_task_ids:
        flash("Select at least one eligible task to run Wadhwani inference.", "warning")
        return redirect(url_for("grading.wadhwani_glaucoma_inference_page"))
    if len(selected_task_ids) > MAX_MANUAL_WADHWANI_BATCH:
        flash(f"Select at most {MAX_MANUAL_WADHWANI_BATCH} tasks per run.", "warning")
        return redirect(url_for("grading.wadhwani_glaucoma_inference_page"))

    with get_db_session() as db:
        integration = get_linked_wadhwani_integration(db)
        if integration is None:
            flash("No linked Wadhwani glaucoma model is configured.", "danger")
            return redirect(url_for("grading.wadhwani_glaucoma_inference_page"))

        allowed_lab_unit_ids = [lab.id for lab in _allowed_lab_units(db)]
        eligible_task_ids = filter_still_eligible_task_ids(
            db,
            ai_model_id=integration.ai_model_id,
            allowed_lab_unit_ids=allowed_lab_unit_ids,
            task_ids=selected_task_ids,
        )
        if not eligible_task_ids:
            flash("No selected tasks remain eligible for Wadhwani inference.", "warning")
            return redirect(url_for("grading.wadhwani_glaucoma_inference_page"))

        task_refs = [f"task:{task_id}" for task_id in eligible_task_ids]
        xff = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
        ip = xff or (request.remote_addr or "-")
        job_token = db_create_job(
            task_refs,
            [],
            uploader_user_id=current_user.id,
            uploader_username=getattr(current_user, "username", None),
            uploader_ip=ip,
            upload_type=WADHWANI_JOB_TYPE,
        )
        job = db.execute(select(Job).where(Job.token == job_token)).scalar_one()
        job.rejected_summary = json.dumps(
            {
                "task_ids": eligible_task_ids,
                "source": "manual_wadhwani_glaucoma_inference",
                "requested_by_user_id": current_user.id,
            }
        )
        db.add(job)

    enqueue_task(
        "celery_tasks.tasks.wadhwani_tasks.run_wadhwani_glaucoma_batch_task",
        job_token,
        eligible_task_ids,
        user_id=current_user.id,
    )
    return redirect(url_for("grading.wadhwani_glaucoma_inference_job_page", job_token=job_token))


@roles_required("admin", "local_admin", "data_manager")
def wadhwani_glaucoma_inference_job_page(job_token: str):
    with get_db_session() as db:
        if _load_wadhwani_job_payload(db, job_token) is None:
            abort(404)
    return render_template(
        "grading/wadhwani_glaucoma_job.html",
        job_token=job_token,
        page_title="Wadhwani Glaucoma Batch Status",
    )


@roles_required("admin", "local_admin", "data_manager")
def wadhwani_glaucoma_inference_job_status_partial(job_token: str):
    with get_db_session() as db:
        payload = _load_wadhwani_job_payload(db, job_token)
        if payload is None:
            abort(404)
    return (
        render_template("grading/_wadhwani_glaucoma_job_status.html", job=payload),
        286 if payload["done"] else 200,
    )


def _allowed_lab_units(db) -> list[LabUnit]:
    query = select(LabUnit).order_by(LabUnit.hospital_id, LabUnit.name)
    query = clinical_lab_units(db, query, current_user)
    return db.execute(query).scalars().all()


def _filters_from_request(args) -> dict[str, str]:
    return {
        "source_type": (args.get("source_type") or "").strip().lower(),
        "lab_unit_id": args.get("lab_unit_id", ""),
        "limit": args.get("limit", str(DEFAULT_MANUAL_WADHWANI_LIMIT)),
        "final_grade_name": args.get("final_grade_name", ""),
        "final_grade_basis": (args.get("final_grade_basis") or "double_match").strip().lower(),
        "zip_camera_id": args.get("zip_camera_id", ""),
        "laterality": args.get("laterality", ""),
        "centering": args.get("centering", ""),
        "remedio_result": args.get("remedio_result", ""),
        "vcdr_min": args.get("vcdr_min", ""),
        "vcdr_max": args.get("vcdr_max", ""),
        "capture_date_from": args.get("capture_date_from", ""),
        "capture_date_to": args.get("capture_date_to", ""),
        "hospital_id": args.get("hospital_id", ""),
        "direct_camera_id": args.get("direct_camera_id", ""),
        "upload_date_from": args.get("upload_date_from", ""),
        "upload_date_to": args.get("upload_date_to", ""),
    }


def _selected_task_ids_from_request() -> list[int]:
    task_ids: list[int] = []
    for raw_value in request.form.getlist("selected_task_ids"):
        try:
            task_ids.append(int(raw_value))
        except (TypeError, ValueError):
            continue
    return list(dict.fromkeys(task_ids))


def _load_wadhwani_job_payload(db, job_token: str) -> dict | None:
    job = db.execute(
        select(Job)
        .where(Job.token == job_token)
        .where(Job.upload_type == WADHWANI_JOB_TYPE)
    ).scalar_one_or_none()
    if job is None:
        return None

    allowed_lab_unit_ids = {lab.id for lab in _allowed_lab_units(db)}
    is_admin = current_user.has_role("admin")
    is_owner = job.uploader_user_id == current_user.id
    if job.lab_unit_id is not None and not (is_admin or is_owner):
        if job.lab_unit_id not in allowed_lab_unit_ids:
            return None

    items = db.execute(
        select(JobItem)
        .where(JobItem.job_id == job.id)
        .order_by(JobItem.id)
    ).scalars().all()

    task_ids: list[int] = []
    for item in items:
        if not item.filename.startswith("task:"):
            continue
        try:
            task_ids.append(int(item.filename.split(":", 1)[1]))
        except ValueError:
            continue

    from models import AIInferenceRun, Grade, GradingTask, DirectImageUpload, EncounterFile, PatientEncounters

    task_models = db.execute(
        select(GradingTask)
        .options(
            selectinload(GradingTask.lab_unit).selectinload(LabUnit.hospital),
            selectinload(GradingTask.encounter_file).selectinload(EncounterFile.camera),
            selectinload(GradingTask.encounter_file).selectinload(EncounterFile.patient_encounter).selectinload(PatientEncounters.zip_file),
            selectinload(GradingTask.direct_image).selectinload(DirectImageUpload.camera),
            selectinload(GradingTask.direct_image).selectinload(DirectImageUpload.hospital),
        )
        .where(GradingTask.id.in_(task_ids))
    ).scalars().all()
    tasks_by_id = {task.id: task for task in task_models}

    # A NULL job Lab Unit is not global access. The one feature-specific
    # exception requires complete, authorized task lineage for every item.
    if job.lab_unit_id is None and not (is_admin or is_owner):
        if (
            not items
            or len(task_ids) != len(items)
            or len(tasks_by_id) != len(set(task_ids))
            or any(
                task.lab_unit_id is None or task.lab_unit_id not in allowed_lab_unit_ids
                for task in tasks_by_id.values()
            )
        ):
            return None

    parsed_by_item_id: dict[int, dict] = {}
    grade_ids: list[int] = []
    inference_run_ids: list[int] = []
    for item in items:
        parsed: dict = {}
        if item.detail:
            try:
                parsed = json.loads(item.detail)
            except json.JSONDecodeError:
                parsed = {"message": item.detail}
        parsed_by_item_id[item.id] = parsed
        grade_id = parsed.get("grade_id")
        run_id = parsed.get("inference_run_id")
        if isinstance(grade_id, int):
            grade_ids.append(grade_id)
        if isinstance(run_id, int):
            inference_run_ids.append(run_id)

    grades_by_id = {
        grade.id: grade
        for grade in db.execute(select(Grade).where(Grade.id.in_(grade_ids))).scalars().all()
    } if grade_ids else {}
    runs_by_id = {
        run.id: run
        for run in db.execute(select(AIInferenceRun).where(AIInferenceRun.id.in_(inference_run_ids))).scalars().all()
    } if inference_run_ids else {}

    item_payloads = []
    summary = {"queued": 0, "processing": 0, "ok": 0, "error": 0}
    for item in items:
        state = (item.state or "queued").lower()
        summary[state if state in summary else "queued"] = summary.get(state if state in summary else "queued", 0) + 1
        parsed = parsed_by_item_id.get(item.id, {})
        task_id = None
        if item.filename.startswith("task:"):
            try:
                task_id = int(item.filename.split(":", 1)[1])
            except ValueError:
                task_id = None
        task = tasks_by_id.get(task_id) if task_id else None
        grade = grades_by_id.get(parsed.get("grade_id")) if isinstance(parsed.get("grade_id"), int) else None
        inference_run = runs_by_id.get(parsed.get("inference_run_id")) if isinstance(parsed.get("inference_run_id"), int) else None
        probability = None
        if grade and grade.comment:
            match = AI_PROBABILITY_PATTERN.search(grade.comment)
            if match:
                probability = match.group(1)
        result_row = {}
        if inference_run and inference_run.execute_response_json:
            results = inference_run.execute_response_json.get("results") or []
            if results:
                result_row = results[0] or {}
        item_payloads.append(
            {
                "task_id": task_id,
                "task_uuid": task.uuid if task else None,
                "state": state,
                "message": parsed.get("message"),
                "grade_id": parsed.get("grade_id"),
                "inference_run_id": parsed.get("inference_run_id"),
                "error_code": parsed.get("error_code"),
                "grade_name": grade.grade_name if grade else None,
                "probability": probability,
                "prediction": result_row.get("prediction"),
                "confidence": result_row.get("confidence"),
                "model_score": result_row.get("model_score"),
                "predicted_class": result_row.get("predicted_class"),
                "predicted_class_name": result_row.get("predicted_class_name"),
                "image_filename": (
                    task.encounter_file.filename
                    if task and task.encounter_file
                    else (task.direct_image.edited_filename or task.direct_image.filename)
                    if task and task.direct_image
                    else None
                ),
                "source_type": "ZIP" if task and task.encounter_file else "Direct" if task and task.direct_image else None,
                "lab_unit_name": task.lab_unit.name if task and task.lab_unit else None,
                "hospital_name": task.lab_unit.hospital.name if task and task.lab_unit and task.lab_unit.hospital else None,
            }
        )

    return {
        "token": job.token,
        "status": job.status,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "items": item_payloads,
        "summary": summary,
        "done": str(job.status or "").lower() in {"done", "error", "partial"},
    }
