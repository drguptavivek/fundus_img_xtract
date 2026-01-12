"""Routes for search images."""

from __future__ import annotations

import re
from typing import Any, List, Optional, Dict
from types import SimpleNamespace

from flask import abort, current_app, render_template, request, url_for, flash, redirect
from flask_login import current_user
from auth.roles import roles_required

from . import bp
from models import Disease, LabUnit, DiseaseGrading, AIModel, Grade, GradingTask
from sqlalchemy.orm import joinedload
from utils.hospital_scoping import apply_scoping
from db_transaction_manager import get_db_session
from utils.mvw_all_img_search import (
    MVImageFilters,
    search_mvw_images,
)
from utils.taskUtils import get_task_detail
from utils.date_utils import parse_date_yyyy_mm_dd
from utils.log_sanitize import sanitize_log_value, mask_text_emails


@bp.route("/images", methods=["GET"])
@bp.route("/images/", methods=["GET"])
@roles_required(
    "admin",
    "local_admin",
    "fileUploader",
    "ophthalmologist",
    "data_manager",
    "resident",
    "optometrist",
)
def search_images_route() -> str:
    """Search images using the MV-backed discrepancy filters for reuse."""
    page = max(1, request.args.get("page", default=1, type=int) or 1)
    per_page = request.args.get("per_page", default=25, type=int)
    per_page = per_page if isinstance(per_page, int) and per_page > 0 else 25
    explicit_offset = request.args.get("offset", type=int)
    offset = explicit_offset if explicit_offset is not None and explicit_offset >= 0 else (page - 1) * per_page

    disease_id = request.args.get("disease_id", type=int)
    lab_unit_id = request.args.get("lab_unit_id", type=int)
    has_consensus = request.args.get("has_consensus", type=str)
    if has_consensus is None:
        has_consensus = "has_consensus"
    has_review = request.args.get("has_review", type=str)
    review_grades = request.args.getlist("review_grade")
    resident_grades = request.args.getlist("resident_grade")
    resident2_grades = request.args.getlist("resident2_grade")
    arbitrator_grades = request.args.getlist("arbitrator_grade")
    final_grades = request.args.getlist("final_grade")
    has_ai_grade = request.args.get("has_ai_grade", type=str)
    ai_model_ids = request.args.getlist("ai_model_id")
    ai_grades = request.args.getlist("ai_grade")
    ai_review_statuses = [
        status for status in request.args.getlist("ai_review_status") if status in AI_REVIEW_STATUS_LABELS
    ]
    image_uuid = (request.args.get("image_uuid") or "").strip() or None
    upload_after = parse_date_yyyy_mm_dd(request.args.get("upload_after"))
    upload_before = parse_date_yyyy_mm_dd(request.args.get("upload_before"))
    encounter_after = parse_date_yyyy_mm_dd(request.args.get("encounter_after"))
    encounter_before = parse_date_yyyy_mm_dd(request.args.get("encounter_before"))

    # Log search request safely
    current_app.logger.info(
        "Search images request - User: %s, Page: %s, Disease: %s, LabUnit: %s, Search: %s",
        sanitize_log_value(current_user.id),
        sanitize_log_value(page),
        sanitize_log_value(disease_id),
        sanitize_log_value(lab_unit_id),
        sanitize_log_value(image_uuid)
    )

    with get_db_session() as db:
        # Get allowed lab units via scoping
        lu_query = db.query(LabUnit)
        lu_query = apply_scoping(lu_query, LabUnit, current_user, "view")
        allowed_lab_unit_ids = [lu.id for lu in lu_query.all()]
        if not allowed_lab_unit_ids:
            flash("No lab unit access.", "warning")
            return redirect(url_for("home.index"))

        disease_grade_map: Dict[int, List[str]] = {}
        all_grade_rows = (
            db.query(DiseaseGrading.disease_id, DiseaseGrading.impression)
            .distinct(DiseaseGrading.disease_id, DiseaseGrading.impression)
            .order_by(DiseaseGrading.disease_id, DiseaseGrading.impression)
            .all()
        )
        for d_id, impression in all_grade_rows:
            disease_grade_map.setdefault(d_id, []).append(impression)
        grade_options = [
            SimpleNamespace(impression=imp) for imp in disease_grade_map.get(disease_id, [])
        ]
        ai_models = db.query(AIModel).order_by(AIModel.name, AIModel.version).all()
        diseases_all = db.query(Disease).order_by(Disease.name).all()

        lab_unit_objs = (
            db.query(LabUnit)
            .options(joinedload(LabUnit.hospital))
            .filter(LabUnit.id.in_(list(allowed_lab_unit_ids)))
            .order_by(LabUnit.name)
            .all()
        )

        if lab_unit_id and lab_unit_id not in allowed_lab_unit_ids:
            from flask import abort
            abort(403, description="Access denied to this lab unit")

        if not disease_id:
            flash("Disease selection is required to search images.", "error")
            return render_template(
                "search/search_images.html",
                rows=[],
                page=page,
                total=0,
                total_pages=0,
                prev_url=None,
                next_url=None,
                filters={
                    "disease_id": disease_id,
                    "lab_unit_id": lab_unit_id,
                    "has_consensus": has_consensus,
                    "has_review": has_review,
                    "review_grade": review_grades,
                    "resident_grade": resident_grades,
                    "resident2_grade": resident2_grades,
                    "arbitrator_grade": arbitrator_grades,
                    "final_grade": final_grades,
                    "has_ai_grade": has_ai_grade,
                    "ai_model_id": ai_model_ids,
                    "ai_grade": ai_grades,
                    "ai_review_status": ai_review_statuses,
                    "image_uuid": image_uuid,
                    "upload_after": request.args.get("upload_after", ""),
                    "upload_before": request.args.get("upload_before", ""),
                    "encounter_after": request.args.get("encounter_after", ""),
                    "encounter_before": request.args.get("encounter_before", ""),
                    "per_page": per_page,
                    "offset": offset,
                },
                grade_options=grade_options,
                ai_models=ai_models,
                lab_units=lab_unit_objs,
                diseases=diseases_all,
                ai_review_status_labels=AI_REVIEW_STATUS_LABELS,
                disease_grade_map=disease_grade_map,
                fundus_api_disease_endpoint="fundus_api.diseases_with_gradings" in current_app.view_functions,
            )

        filters = MVImageFilters(
            disease_id=disease_id,
            allowed_lab_units=list(allowed_lab_unit_ids),
            lab_unit_id=lab_unit_id,
            resident_grades=resident_grades,
            resident2_grades=resident2_grades,
            arbitrator_grades=arbitrator_grades,
            review_grades=review_grades,
            final_grades=final_grades,
            has_ai_grade=has_ai_grade,
            has_review=has_review,
            has_consensus=has_consensus,
            ai_model_ids=ai_model_ids,
            ai_grades=ai_grades,
            ai_review_statuses=ai_review_statuses,
            image_uuid=image_uuid,
            upload_after=upload_after,
            upload_before=upload_before,
            encounter_after=encounter_after,
            encounter_before=encounter_before,
        )

        rows, total = search_mvw_images(db, filters, per_page=per_page, offset=offset)

        processed_rows: List[Dict[str, Any]] = []
        task_ids = [row.task_id for row in rows]
        ai_review_comments: Dict[int, List[str]] = {}
        ai_review_statuses: Dict[int, List[str]] = {}
        if task_ids:
            comment_rows = (
                db.query(Grade.task_id, Grade.ai_review_comment, Grade.ai_review_status)
                .filter(Grade.role_slot == "ai", Grade.task_id.in_(task_ids))
                .filter(
                    (Grade.ai_review_comment.isnot(None))
                    | (Grade.ai_review_status.isnot(None))
                )
                .all()
            )
            for task_id, comment, status in comment_rows:
                if comment:
                    ai_review_comments.setdefault(task_id, []).append(comment)
                if status:
                    ai_review_statuses.setdefault(task_id, []).append(status)

        for row in rows:
            grades = _extract_grades_by_role(row.grading_details_json or "[]")
            ai_grade = grades.get("ai")
            if ai_grade:
                if ai_review_comments.get(row.task_id):
                    ai_grade["ai_review_comments"] = ai_review_comments[row.task_id]
                if ai_review_statuses.get(row.task_id):
                    ai_grade["ai_review_statuses"] = ai_review_statuses[row.task_id]
            processed_rows.append(
                {
                    "task_id": row.task_id,
                    "task_uuid": row.task_uuid,
                    "lab_unit_name": row.lab_unit_name,
                    "hospital_name": row.hospital_name,
                    "encounter_file_uuid": row.encounter_file_uuid,
                    "direct_image_uuid": row.direct_image_uuid,
                    "grades": grades,
                    "consensus_status": row.consensus_status,
                    "consensus_method": row.consensus_method,
                    "final_impression": row.final_impression,
                    "ai_grading_count": row.ai_grading_count,
                    "upload_date": row.upload_date,
                    "capture_date": row.capture_date,
                }
            )

        total_pages = max(1, (total + per_page - 1) // per_page) if total else 1
        current_page = offset // per_page + 1

        def _filter_kwargs(target_page: int) -> dict[str, Any]:
            params: dict[str, Any] = {
                "page": target_page,
                "per_page": per_page,
                "offset": (target_page - 1) * per_page,
            }
            params.update(
                {
                    "disease_id": disease_id,
                    "lab_unit_id": lab_unit_id,
                    "has_consensus": has_consensus,
                    "has_review": has_review,
                    "has_ai_grade": has_ai_grade,
                    "image_uuid": image_uuid or "",
                    "upload_after": request.args.get("upload_after", ""),
                    "upload_before": request.args.get("upload_before", ""),
                    "encounter_after": request.args.get("encounter_after", ""),
                    "encounter_before": request.args.get("encounter_before", ""),
                }
            )
            for key in ["resident_grade", "resident2_grade", "arbitrator_grade", "review_grade", "final_grade", "ai_grade", "ai_review_status", "ai_model_id"]:
                for value in request.args.getlist(key):
                    params.setdefault(key, []).append(value)
            return params

        prev_url = (
            url_for("search.search_images_route", **_filter_kwargs(current_page - 1)) if current_page > 1 else None
        )
        next_url = (
            url_for("search.search_images_route", **_filter_kwargs(current_page + 1))
            if current_page < total_pages
            else None
        )

        return render_template(
            "search/search_images.html",
            rows=processed_rows,
            page=current_page,
            total=total,
            total_pages=total_pages,
            prev_url=prev_url,
            next_url=next_url,
            filters={
                "disease_id": disease_id,
                "lab_unit_id": lab_unit_id,
                "has_consensus": has_consensus,
                "has_review": has_review,
                "review_grade": review_grades,
                "resident_grade": resident_grades,
                "resident2_grade": resident2_grades,
                "arbitrator_grade": arbitrator_grades,
                "final_grade": final_grades,
                "has_ai_grade": has_ai_grade,
                "ai_model_id": ai_model_ids,
                "ai_grade": ai_grades,
                "ai_review_status": ai_review_statuses,
                "image_uuid": image_uuid,
                "upload_after": request.args.get("upload_after", ""),
                "upload_before": request.args.get("upload_before", ""),
                "encounter_after": request.args.get("encounter_after", ""),
                "encounter_before": request.args.get("encounter_before", ""),
                "per_page": per_page,
                "offset": offset,
            },
            grade_options=grade_options,
            ai_models=ai_models,
            lab_units=lab_unit_objs,
            diseases=diseases_all,
            ai_review_status_labels=AI_REVIEW_STATUS_LABELS,
            disease_grade_map=disease_grade_map,
            fundus_api_disease_endpoint="fundus_api.diseases_with_gradings" in current_app.view_functions,
        )


@bp.route("/images/<int:task_id>/view", methods=["GET"])
@roles_required(
    "admin",
    "local_admin",
    "fileUploader",
    "ophthalmologist",
    "data_manager",
    "resident",
    "optometrist",
)
def search_image_detail(task_id: int) -> str:
    """Read-only task detail view for search results with inline image viewer."""
    with get_db_session() as db:
        # Get allowed lab units via scoping
        lu_query = db.query(LabUnit)
        lu_query = apply_scoping(lu_query, LabUnit, current_user, "view")
        allowed_lab_unit_ids = [lu.id for lu in lu_query.all()]
        if not allowed_lab_unit_ids:
            flash("No lab unit access.", "warning")
            return redirect(url_for("home.index"))

        task = (
            db.query(GradingTask)
            .options(
                joinedload(GradingTask.disease),
                joinedload(GradingTask.lab_unit).joinedload(LabUnit.hospital),
                joinedload(GradingTask.encounter_file),
                joinedload(GradingTask.direct_image),
                joinedload(GradingTask.grades),
            )
            .filter(GradingTask.id == task_id, GradingTask.lab_unit_id.in_(allowed_lab_unit_ids))
            .first()
        )
        if not task:
            abort(404, description="Task not found or access denied")

        task_details = get_task_detail(db, task_id)
        if not task_details:
            abort(404, description="Task not found or access denied")

        image_object = task.encounter_file if task.encounter_file else task.direct_image
        grade_by_role = {grade.role_slot: grade for grade in task.grades or []}

        return render_template(
            "search/search_image_detail.html",
            task=task_details,
            original_task=task,
            image_object=image_object,
            grade_by_role=grade_by_role,
            return_to=request.args.get("return_to"),
        )


def _extract_grades_by_role(details_json: str) -> Dict[str, Dict[str, Any]]:
    """Parse MV JSON details into role-keyed dict for templates."""
    import json
    if isinstance(details_json, str):
        try:
            grades = json.loads(details_json)
        except Exception:
            return {}
    else:
        grades = details_json or []
    result: Dict[str, Dict[str, Any]] = {}
    for item in grades or []:
        role = item.get("role_slot")
        if not role:
            continue
        grade_entry: Dict[str, Any] = {
            "impression": item.get("grade_name"),
            "comment": mask_text_emails(item.get("comment")),
            "ai_model_name": item.get("ai_model_name"),
            "ai_model_version": item.get("ai_model_version"),
        }
        if role == "ai":
            comment = mask_text_emails(item.get("comment")) or ""
            provided_prob = (
                item.get("ai_probability")
                or item.get("ai_prob")
                or item.get("probability")
            )
            prob_value = _extract_ai_probability(comment, provided_prob)
            if prob_value is None and comment:
                fallback_match = re.search(r"([0-9]+(?:\.[0-9]+)?)", comment)
                if fallback_match:
                    try:
                        prob_value = float(fallback_match.group(1))
                    except Exception:
                        prob_value = fallback_match.group(1)
            grade_entry["ai_probability"] = prob_value
            grade_entry["comment"] = comment
        result[role] = grade_entry
    return result


def _extract_ai_probability(comment: str | None, provided: Any | None) -> float | str | None:
    """
    Extract AI probability, normalising to float when possible.

    Priority order:
    1. Explicit provided value (ai_probability / ai_prob / probability)
    2. Parse from comment if it contains a numeric "AI probability" fragment.
    """
    candidate = provided
    if candidate is None and comment:
        match = re.search(
            r"AI\s*probability\s*[:=]?\s*([0-9]*\.?[0-9]+)",
            comment,
            flags=re.IGNORECASE,
        )
        if match:
            candidate = match.group(1)
    if candidate is None:
        return None
    try:
        return float(candidate)
    except Exception:
        return str(candidate)
