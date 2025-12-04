from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from flask import abort, jsonify, render_template, request, send_file
from flask_login import current_user
from sqlalchemy import and_, or_, text
from sqlalchemy.orm import joinedload, selectinload

from auth.roles import roles_required
from job_store import db_create_job
from models import (
    AIModel,
    Consensus,
    Disease,
    DiseaseGrading,
    Grade,
    GradingTask,
    Job,
    Hospital,
    LabUnit,
    Session,
    User,
)
from utils.upload_eligibility import (
    get_user_lab_unit_ids,
    get_user_lab_unit_ids_no_admin_override,
)
from .discrepancy_export import enqueue_discrepancy_export, EXPORT_DIR
from . import bp


@bp.route("/discrepancy-review", methods=["GET"])
@roles_required("admin", "local_admin", "data_manager")
def discrepancy_review():
    """Main page for discrepancy review process.

    Note: Even though this route requires admin or data_manager roles,
    we still scope the lab units to the logged-in user to ensure
    data access is properly restricted. Admin users will see all
    lab units, while data_managers will only see their assigned units.
    """
    db = Session()
    try:
        # Scope lab units to user's explicit associations (no admin override)
        user_lab_unit_ids = get_user_lab_unit_ids_no_admin_override(current_user.id)
        
        # Get filter options
        diseases = db.query(Disease).order_by(Disease.name).all()
        lab_units = db.query(LabUnit).filter(LabUnit.id.in_(list(user_lab_unit_ids))).options(joinedload(LabUnit.hospital)).order_by(LabUnit.hospital_id, LabUnit.name).all()
        
        # Get grade options from DiseaseGrading
        grade_options = db.query(DiseaseGrading).distinct(DiseaseGrading.impression).all()
        
        # Get AI models for the AI model filter
        ai_models = db.query(AIModel).order_by(AIModel.name, AIModel.version).all()
        
        # Apply filters
        query = db.query(GradingTask).filter(GradingTask.lab_unit_id.in_(list(user_lab_unit_ids)))
        
        # Apply disease filter (mandatory)
        from flask import flash, redirect, url_for, request, session
        disease_id = request.args.get("disease_id", type=int)
        
        # Check if we're already being redirected (no disease_id but error message in session)
        if not disease_id and not session.get('_disease_error_shown'):
            # Mark that we've shown the error to prevent infinite redirects
            session['_disease_error_shown'] = True
            flash("Disease selection is required for discrepancy review", "error")
            # Preserve other query parameters when redirecting
            query_params = request.args.to_dict()
            query_params = {k: v for k, v in query_params.items() if k != 'disease_id'}
            return redirect(url_for('review.discrepancy_review', **query_params))
        
        # Clear the error flag if disease is selected
        if disease_id and session.get('_disease_error_shown'):
            session.pop('_disease_error_shown', None)
        
        query = query.filter(GradingTask.disease_id == disease_id)
        
        # Apply lab unit filter
        lab_unit_id = request.args.get("lab_unit_id", type=int)
        if lab_unit_id:
            query = query.filter(GradingTask.lab_unit_id == lab_unit_id)
        
        # Get grade filter values (as lists to support multi-select)
        resident_grades = request.args.getlist("resident_grade")
        resident2_grades = request.args.getlist("resident2_grade")
        arbitrator_grades = request.args.getlist("arbitrator_grade")
        final_grades = request.args.getlist("final_grade")
        
        # Get AI grade filter
        has_ai_grade = request.args.get("has_ai_grade", type=str)
        
        # Get review grade filter
        has_review = request.args.get("has_review", type=str)
        
        # Get consensus filter
        has_consensus = request.args.get("has_consensus", default="has_consensus", type=str)
        
        # Get AI model filter
        ai_model_ids = request.args.getlist("ai_model_id")

        # AI grade filter (multi-select, optional)
        ai_grades = request.args.getlist("ai_grade")

        # If user didn't request AI-grade-only records, ignore AI-specific filters
        if has_ai_grade != "yes":
            ai_model_ids = []
            ai_grades = []

        # Figure out which MV columns to use based on disease
        disease_key = _resolve_disease_key(db, disease_id)
        mv_detail_col = f"{disease_key}_grading_details_json"
        mv_ai_count_col = f"{disease_key}_ai_grading_count"
        mv_consensus_col = f"{disease_key}_consensus_status"

        # Restrict to lab units the user can access (via GradingTask.lab_unit_id)
        allowed_lab_units = list(user_lab_unit_ids)
        if not allowed_lab_units:
            return render_template(
                "review/discrepancy_review.html",
                diseases=diseases,
                lab_units=[],
                grade_options=grade_options,
                ai_models=ai_models,
                tasks=[],
                total_count=0,
                page=1,
                total_pages=0,
                has_prev=False,
                has_next=False,
                filters={},
            )

        # Allow only one AI model selection at a time (pick the first if multiple)
        selected_ai_model_id: Optional[int] = None
        if ai_model_ids:
            cleaned_models = [mid for mid in ai_model_ids if mid]
            if cleaned_models:
                selected_ai_model_id = int(cleaned_models[0])
                ai_model_ids = [str(selected_ai_model_id)]
            else:
                ai_model_ids = []

        # Build dynamic WHERE clauses
        where_clauses: List[str] = [
            "gt.disease_id = :disease_id",
            "gt.lab_unit_id = ANY(:allowed_lab_units)",
        ]
        params: Dict[str, Any] = {
            "disease_id": disease_id,
            "allowed_lab_units": allowed_lab_units,
        }

        if lab_unit_id and lab_unit_id in user_lab_unit_ids:
            where_clauses.append("gt.lab_unit_id = :lab_unit_id")
            params["lab_unit_id"] = lab_unit_id

        # Consensus filter
        if has_consensus == "has_consensus":
            where_clauses.append("c.id IS NOT NULL")
        elif has_consensus == "no":
            where_clauses.append("c.id IS NULL")

        # Review filter (exists in MV JSON)
        if has_review == "yes":
            where_clauses.append(
                f"EXISTS (SELECT 1 FROM jsonb_array_elements({mv_detail_col}::jsonb) elem WHERE elem->>'role_slot' = 'review')"
            )
        elif has_review == "no":
            where_clauses.append(
                f"NOT EXISTS (SELECT 1 FROM jsonb_array_elements({mv_detail_col}::jsonb) elem WHERE elem->>'role_slot' = 'review')"
            )

        # Has AI grade filter
        if has_ai_grade == "yes":
            where_clauses.append(f"{mv_ai_count_col} > 0")
        elif has_ai_grade == "no":
            where_clauses.append(f"{mv_ai_count_col} = 0")

        # Role-specific grade filters (resident, resident2, arbitrator) via MV JSON
        role_grade_filters = [
            ("resident", resident_grades),
            ("resident2", resident2_grades),
            ("arbitrator", arbitrator_grades),
        ]
        for role, impressions in role_grade_filters:
            if impressions:
                valid_impressions = [g for g in impressions if g]
                if valid_impressions:
                    where_clauses.append(
                        f"EXISTS (SELECT 1 FROM jsonb_array_elements({mv_detail_col}::jsonb) elem "
                        "WHERE elem->>'role_slot' = :role_slot_"
                        + role
                        + " AND elem->>'grade_name' = ANY(:grade_names_"
                        + role
                        + "))"
                    )
                    params[f"role_slot_{role}"] = role
                    params[f"grade_names_{role}"] = valid_impressions

        # AI model filter (single model enforced)
        if selected_ai_model_id is not None:
            where_clauses.append(
                f"EXISTS (SELECT 1 FROM jsonb_array_elements({mv_detail_col}::jsonb) elem "
                "WHERE elem->>'role_slot' = 'ai' AND (elem->>'ai_model_id')::int = :ai_model_id)"
            )
            params["ai_model_id"] = selected_ai_model_id

        # AI grade filter (multiple values)
        if ai_grades:
            valid_ai_grades = [g for g in ai_grades if g]
            if valid_ai_grades:
                where_clauses.append(
                    f"EXISTS (SELECT 1 FROM jsonb_array_elements({mv_detail_col}::jsonb) elem "
                    "WHERE elem->>'role_slot' = 'ai' AND elem->>'grade_name' = ANY(:ai_grade_names))"
                )
                params["ai_grade_names"] = valid_ai_grades

        # Final grade filter via consensus
        if final_grades:
            valid_final_grades = [g for g in final_grades if g]
            if valid_final_grades:
                where_clauses.append("dg.impression = ANY(:final_grades)")
                params["final_grades"] = valid_final_grades

        where_sql = " AND ".join(where_clauses)

        base_query = f"""
            FROM mvw_image_listing_all v
            JOIN grading_tasks gt ON (
                (v.direct_image_upload_id IS NOT NULL AND gt.direct_image_upload_id = v.direct_image_upload_id) OR
                (v.encounter_file_id IS NOT NULL AND gt.encounter_file_id = v.encounter_file_id)
            )
            LEFT JOIN lab_units lu ON gt.lab_unit_id = lu.id
            LEFT JOIN hospitals h ON lu.hospital_id = h.id
            LEFT JOIN encounter_files ef ON gt.encounter_file_id = ef.id
            LEFT JOIN direct_image_uploads diu ON gt.direct_image_upload_id = diu.id
            LEFT JOIN consensus c ON gt.id = c.task_id
            LEFT JOIN disease_gradings dg ON c.final_disease_grading_id = dg.id
            WHERE {where_sql}
        """

        # Total count for pagination
        count_sql = f"SELECT COUNT(*) {base_query}"
        total_count = db.execute(text(count_sql), params).scalar() or 0

        # Pagination setup
        page = request.args.get("page", 1, type=int)
        per_page = 50
        offset = (page - 1) * per_page

        data_sql = f"""
            SELECT
                gt.id AS task_id,
                gt.state,
                gt.lab_unit_id,
                lu.name AS lab_unit_name,
                h.name AS hospital_name,
                gt.encounter_file_id,
                ef.uuid AS encounter_file_uuid,
                gt.direct_image_upload_id,
                diu.uuid AS direct_image_uuid,
                {mv_detail_col} AS grading_details_json,
                {mv_consensus_col} AS consensus_status,
                {mv_ai_count_col} AS ai_grading_count,
                c.id AS consensus_id,
                dg.impression AS final_impression,
                c.method AS consensus_method
            {base_query}
            ORDER BY gt.id DESC
            LIMIT :limit OFFSET :offset
        """
        params.update({"limit": per_page, "offset": offset})

        rows = db.execute(text(data_sql), params).fetchall()

        processed_tasks = []
        queue_ids = [row.task_id for row in rows]
        ai_review_comments: Dict[int, List[str]] = defaultdict(list)
        ai_review_statuses: Dict[int, List[str]] = defaultdict(list)
        if queue_ids:
            ai_review_rows = (
                db.query(Grade.task_id, Grade.ai_review_comment, Grade.ai_review_status)
                .filter(Grade.role_slot == "ai", Grade.task_id.in_(queue_ids))
                .filter(or_(Grade.ai_review_comment.isnot(None), Grade.ai_review_status.isnot(None)))
                .all()
            )
            for task_id, comment, status in ai_review_rows:
                if comment:
                    ai_review_comments[task_id].append(comment)
                if status:
                    ai_review_statuses[task_id].append(status)

        queue_len = len(queue_ids)
        for idx, row in enumerate(rows):
            grades_by_role = _extract_grades_by_role(row.grading_details_json or "[]")
            if "ai" in grades_by_role:
                if ai_review_comments.get(row.task_id):
                    grades_by_role["ai"]["ai_review_comments"] = ai_review_comments[row.task_id]
                if ai_review_statuses.get(row.task_id):
                    grades_by_role["ai"]["ai_review_statuses"] = ai_review_statuses[row.task_id]
            next_task_id = queue_ids[idx + 1] if idx + 1 < queue_len else None
            next_after_task_id = queue_ids[idx + 2] if idx + 2 < queue_len else None
            task_data = {
                "id": row.task_id,
                "state": row.state,
                "disease_name": next((d.name for d in diseases if d.id == disease_id), None),
                "lab_unit_name": row.lab_unit_name,
                "hospital_name": row.hospital_name,
                "encounter_file_uuid": row.encounter_file_uuid,
                "direct_image_uuid": row.direct_image_uuid,
                "grades": grades_by_role,
                "consensus": None,
                "next_task_id": next_task_id,
                "next_after_task_id": next_after_task_id,
            }
            if row.consensus_id:
                task_data["consensus"] = {
                    "id": row.consensus_id,
                    "impression": row.final_impression,
                    "method": row.consensus_method,
                }
            processed_tasks.append(task_data)

        total_pages = (total_count + per_page - 1) // per_page
        has_prev = page > 1
        has_next = page < total_pages

        return render_template(
            "review/discrepancy_review.html",
            diseases=diseases,
            lab_units=lab_units,
            grade_options=grade_options,
            ai_models=ai_models,
            tasks=processed_tasks,
            total_count=total_count,
            page=page,
            total_pages=total_pages,
            has_prev=has_prev,
            has_next=has_next,
            filters={
                "disease_id": disease_id,
                "lab_unit_id": lab_unit_id,
                "resident_grade": resident_grades,
                "resident2_grade": resident2_grades,
                "arbitrator_grade": arbitrator_grades,
                "final_grade": final_grades,
                "has_ai_grade": has_ai_grade,
                "has_review": has_review,
                "has_consensus": has_consensus,
                "ai_model_id": ai_model_ids,
                "ai_grade": ai_grades,
            },
        )
    finally:
        db.close()


@bp.route("/discrepancy-export", methods=["POST"])
@roles_required("admin", "local_admin", "data_manager")
def discrepancy_export():
    """Queue a background export for the current discrepancy filters."""
    db = Session()
    try:
        user_lab_unit_ids = get_user_lab_unit_ids_no_admin_override(current_user.id)
        if not user_lab_unit_ids:
            from flask import flash, redirect, url_for
            flash("No lab units available for export.", "error")
            return redirect(url_for("review.discrepancy_review"))
        disease_id = request.form.get("disease_id", type=int)
        if not disease_id:
            from flask import flash, redirect, url_for
            flash("Disease selection is required for export.", "error")
            return redirect(url_for("review.discrepancy_review", **request.args))

        lab_unit_id = request.form.get("lab_unit_id", type=int)
        if lab_unit_id and lab_unit_id not in user_lab_unit_ids:
            from flask import flash, redirect, url_for
            flash("You are not allowed to export for this lab unit.", "error")
            return redirect(url_for("review.discrepancy_review", **request.args))

        filters = {
            "disease_id": disease_id,
            "lab_unit_id": lab_unit_id,
            "resident_grade": request.form.getlist("resident_grade"),
            "resident2_grade": request.form.getlist("resident2_grade"),
            "arbitrator_grade": request.form.getlist("arbitrator_grade"),
            "final_grade": request.form.getlist("final_grade"),
            "has_ai_grade": request.form.get("has_ai_grade", type=str),
            "has_review": request.form.get("has_review", type=str),
            "has_consensus": request.form.get("has_consensus", default="has_consensus", type=str),
            "ai_model_id": request.form.getlist("ai_model_id"),
            "ai_grade": request.form.getlist("ai_grade"),
            "allowed_lab_units": list(user_lab_unit_ids),
        }

        xff = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
        ip = xff or (request.remote_addr or "-")
        uploader_username = getattr(current_user, "username", None)
        uploader_user_id = getattr(current_user, "id", None)
        job_token = db_create_job(
            ["discrepancy_export"],
            [],
            uploader_user_id=uploader_user_id,
            uploader_username=uploader_username,
            uploader_ip=ip,
            lab_unit_id=lab_unit_id,
            upload_type="discrepancy_export",
        )
        from flask import current_app, flash, redirect, url_for

        enqueue_discrepancy_export(current_app._get_current_object(), job_token, filters, {"user_id": current_user.id})
        flash("Export queued. You can monitor progress in Jobs.", "info")
        return redirect(url_for("jobs.job_status_page", job_token=job_token))
    finally:
        db.close()

@bp.route("/discrepancy-export/<job_token>/<path:filename>", methods=["GET"])
@roles_required("admin", "local_admin", "data_manager")
def discrepancy_export_download(job_token: str, filename: str):
    """Serve generated export artifacts (Excel or zip) for authorized users."""
    with Session() as db:
        job = db.query(Job).filter(Job.token == job_token, Job.upload_type == "discrepancy_export").first()
        if not job:
            abort(404)
        allowed_lab_units = get_user_lab_unit_ids_no_admin_override(current_user.id)
        if job.lab_unit_id is None and job.uploader_user_id != current_user.id:
            abort(404)
        if job.lab_unit_id and job.lab_unit_id not in allowed_lab_units and job.uploader_user_id != current_user.id:
            abort(404)

    export_dir = (EXPORT_DIR / job_token).resolve()
    target = (export_dir / filename).resolve()
    if not str(target).startswith(str(export_dir)) or not target.is_file():
        abort(404)

    return send_file(target, as_attachment=True)

def get_disease_grading_id_by_impression(db: Session, impression: str) -> int | None:
    """Helper function to get disease grading ID by impression."""
    from models import DiseaseGrading
    grading = db.query(DiseaseGrading).filter(DiseaseGrading.impression == impression).first()
    return grading.id if grading else None


def _extract_ai_probability(comment: Optional[str], provided: Optional[Any] = None) -> Optional[str]:
    """Return AI probability from provided value or parsed comment."""
    if provided is not None:
        try:
            return str(provided)
        except Exception:
            return None
    if not comment:
        return None
    match = re.search(r"AI probability:\s*([0-9.]+)", comment, flags=re.IGNORECASE)
    return match.group(1) if match else None


def _resolve_disease_key(db: Session, disease_id: int) -> str:
    """Map disease to mvw_image_listing_all column prefix."""
    disease = db.get(Disease, disease_id)
    if not disease:
        return "dr"
    name = (disease.name or "").lower()
    if "glaucoma" in name:
        return "glaucoma"
    if "amd" in name or "macular" in name:
        return "amd"
    return "dr"


def _extract_grades_by_role(details_json: str) -> Dict[str, Dict[str, Any]]:
    """Parse MV JSON details into role-keyed dict for templates."""
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
        result[role] = {
            "id": item.get("grade_id"),
            "impression": item.get("grade_name"),
            "comment": item.get("comment"),
        }
        if role == "ai":
            result[role]["ai_model_name"] = item.get("ai_model_name")
            result[role]["ai_model_version"] = item.get("ai_model_version")
            result[role]["ai_probability"] = _extract_ai_probability(
                item.get("comment"), item.get("ai_probability")
            )
    return result
