from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from flask import abort, jsonify, render_template, request, send_file
from flask_login import current_user, login_required
from sqlalchemy import text

from auth.roles import roles_required
from auth.decorators import require_recent_reauthentication
from authz.behaviors import identifier_release_lab_units
from job_store import db_create_job
from models import (
    AIModel,
    DiseaseGrading,
    Job,
    LabUnit,
    ProjectRoleGrant,
    Role,
    Session,
    User,
    user_lab_units,
)
from db_transaction_manager import get_db_session
from sqlalchemy import select

from encounter_sets.permissions import (
    capability_lab_unit_ids,
)
from utils.discrepancy_filters import (
    AI_REVIEW_STATUS_MISSING,
    build_discrepancy_filter_query,
)
from utils.final_grade_basis import (
    derive_final_grade_source,
    normalize_final_grade_basis,
    sql_final_grade_expression,
)
from regrade.service import authorized_manager_project_grant_ids
from .discrepancy_export import (
    ARTIFACT_SCOPE_FILENAME,
    EXPORT_DIR,
    authorized_export_project_lab_unit_ids,
    authorized_export_project_grant_ids,
    enqueue_discrepancy_export,
    reauthorize_discrepancy_artifact,
)
from . import bp
from .task_review import AI_REVIEW_STATUS_LABELS
from .queues import ReviewQueueError, load_review_queue
from .discrepancy_scope import (
    DiscrepancyScopeError,
    discrepancy_lab_unit_ids,
    list_discrepancy_filter_options,
)

AI_REVIEW_STATUS_FILTER_LABELS = {
    **AI_REVIEW_STATUS_LABELS,
    AI_REVIEW_STATUS_MISSING: "Missing",
}
EXPORT_ROLES = frozenset(
    {"local_admin", "data_manager", "data_exporter", "fileUploader", "optometrist"}
)


def _review_lab_unit_ids(db) -> set[int]:
    return discrepancy_lab_unit_ids(db, user=current_user)


def render_discrepancy_review(
    page_title: str | None = None,
    enforced_filters: Dict[str, str] | None = None,
):
    """Main page for discrepancy review process.

    Note: Even though this route requires admin or data_manager roles,
    we still scope the lab units to the logged-in user to ensure
    data access is properly restricted. Admin users will see all
    lab units, while data_managers will only see their assigned units.
    """
    with get_db_session() as db:
        review_lab_unit_ids = _review_lab_unit_ids(db)
        project_id = request.args.get("project_id", type=int)
        try:
            filter_options = list_discrepancy_filter_options(
                db,
                user=current_user,
                allowed_lab_unit_ids=review_lab_unit_ids,
                project_id=project_id,
            )
        except DiscrepancyScopeError:
            abort(404)
        projects = filter_options.projects
        diseases = filter_options.diseases
        lab_units = filter_options.lab_units
        user_lab_unit_ids = {lu.id for lu in lab_units}
        
        # Get grade options from DiseaseGrading
        grade_options = db.query(DiseaseGrading).distinct(DiseaseGrading.impression).all()
        
        # Get AI models for the AI model filter
        ai_models = db.query(AIModel).order_by(AIModel.name, AIModel.version).all()

        regrade_adjudicators: List[User] = []
        if user_lab_unit_ids:
            classical_user_ids = set(db.execute(
                select(User)
                .join(User.roles)
                .join(user_lab_units, user_lab_units.c.user_id == User.id)
                .where(Role.name == "regrade_adjudicator")
                .where(User.is_active.is_(True))
                .where(user_lab_units.c.lab_unit_id.in_(user_lab_unit_ids))
                .distinct()
            ).scalars().all())
            project_ids = {project.id for project in projects}
            project_user_ids: set[int] = set()
            if project_ids:
                grant_query = (
                    select(ProjectRoleGrant.user_id)
                    .join(Role, Role.id == ProjectRoleGrant.role_id)
                    .where(
                        ProjectRoleGrant.active.is_(True),
                        ProjectRoleGrant.project_id.in_(project_ids),
                        Role.name == "regrade_adjudicator",
                    )
                    .where(
                        (ProjectRoleGrant.scope_type == "project")
                        | (
                            (ProjectRoleGrant.scope_type == "lab_unit")
                            & ProjectRoleGrant.lab_unit_id.in_(user_lab_unit_ids)
                        )
                    )
                    .distinct()
                )
                project_user_ids = set(db.execute(grant_query).scalars().all())
            candidate_ids = classical_user_ids | project_user_ids
            if candidate_ids:
                regrade_adjudicators = db.execute(
                    select(User)
                    .where(User.id.in_(candidate_ids), User.is_active.is_(True))
                    .order_by(User.username)
                ).scalars().all()
        
        # Apply disease filter (mandatory)
        from flask import flash, redirect, url_for, session
        review_queue_token = (request.args.get("review_queue") or "").strip()
        review_queue = None
        if review_queue_token:
            try:
                review_queue = load_review_queue(
                    db, user=current_user, token=review_queue_token
                )
            except ReviewQueueError:
                abort(404)
        disease_id = (
            review_queue.disease_id
            if review_queue is not None
            else request.args.get("disease_id", type=int)
        )
        
        regrade_creator_mode = bool(enforced_filters)
        review_route = "review.regrade_task_creator" if regrade_creator_mode else "review.discrepancy_review"

        # Check if we're already being redirected (no disease_id but error message in session)
        if not disease_id and not session.get('_disease_error_shown'):
            # Mark that we've shown the error to prevent infinite redirects
            session['_disease_error_shown'] = True
            flash("Disease selection is required for discrepancy review", "error")
            # Preserve other query parameters when redirecting
            query_params = request.args.to_dict()
            query_params = {k: v for k, v in query_params.items() if k != 'disease_id'}
            return redirect(url_for(review_route, **query_params))

        # Clear the error flag if disease is selected
        if disease_id and session.get('_disease_error_shown'):
            session.pop('_disease_error_shown', None)

        if not disease_id:
            return render_template(
                "review/discrepancy_review.html",
                projects=projects,
                diseases=diseases,
                lab_units=lab_units,
                grade_options=grade_options,
                ai_models=ai_models,
                regrade_adjudicators=regrade_adjudicators,
                tasks=[],
                total_count=0,
                page=1,
                total_pages=0,
                has_prev=False,
                has_next=False,
                ai_review_status_labels=AI_REVIEW_STATUS_FILTER_LABELS,
                filters={"project_id": project_id},
                page_title=page_title,
                regrade_creator_mode=regrade_creator_mode,
                review_route=review_route,
            )
        
        # Apply lab unit filter
        lab_unit_id = request.args.get("lab_unit_id", type=int)
        if disease_id not in {disease.id for disease in diseases}:
            abort(404)
        if lab_unit_id is not None and lab_unit_id not in user_lab_unit_ids:
            abort(404)
        
        # Get grade filter values (as lists to support multi-select)
        resident_grades = request.args.getlist("resident_grade")
        resident2_grades = request.args.getlist("resident2_grade")
        arbitrator_grades = request.args.getlist("arbitrator_grade")
        final_grades = request.args.getlist("final_grade")
        
        # Get AI grade filter
        has_ai_grade = request.args.get("has_ai_grade", type=str)
        has_human_review = request.args.get("has_human_review", type=str)
        
        # Get review grade filter
        has_review = request.args.get("has_review", type=str)
        review_grades = request.args.getlist("review_grade")
        has_regrade = request.args.get("has_regrade", type=str)
        regrade_grades = request.args.getlist("regrade_grade")
        has_arbitrator = request.args.get("has_arbitrator", type=str)

        # Get consensus filter
        has_consensus = request.args.get("has_consensus", type=str)
        consensus_method = request.args.get("consensus_method", type=str)

        if has_consensus == "no":
            consensus_method = None
            final_grades = []
            has_arbitrator = None
            arbitrator_grades = []
            has_review = None
            review_grades = []
            has_regrade = None
            regrade_grades = []

        # Resident comparison filter
        resident_compare = request.args.get("resident_compare", type=str)

        enforced = enforced_filters or {}
        if enforced:
            # Apply defaults only when filter keys are absent from the query.
            # If a key is present with an empty value (e.g. has_arbitrator=),
            # treat it as "All Tasks" and preserve it.
            if "resident_compare" not in request.args:
                resident_compare = enforced.get("resident_compare", resident_compare)
            if "has_arbitrator" not in request.args:
                has_arbitrator = enforced.get("has_arbitrator", has_arbitrator)
            if "has_regrade" not in request.args:
                has_regrade = enforced.get("has_regrade", has_regrade)
        
        # Get AI model filter
        ai_model_ids = request.args.getlist("ai_model_id")
        final_grade_basis = normalize_final_grade_basis(request.args.get("final_grade_basis"))

        # AI grade filter (multi-select, optional)
        ai_grades = request.args.getlist("ai_grade")
        ai_review_statuses = [
            status
            for status in request.args.getlist("ai_review_status")
            if status in AI_REVIEW_STATUS_FILTER_LABELS
        ]

        # Restrict to lab units the user can access (via GradingTask.lab_unit_id)
        allowed_lab_units = list(user_lab_unit_ids)
        if not allowed_lab_units:
            return render_template(
                "review/discrepancy_review.html",
                projects=projects,
                diseases=diseases,
                lab_units=[],
                grade_options=grade_options,
                ai_models=ai_models,
                regrade_adjudicators=regrade_adjudicators,
                tasks=[],
                total_count=0,
                page=1,
                total_pages=0,
                has_prev=False,
                has_next=False,
                ai_review_status_labels=AI_REVIEW_STATUS_FILTER_LABELS,
                filters={"project_id": project_id},
                page_title=page_title,
                regrade_creator_mode=regrade_creator_mode,
                review_route=review_route,
            )

        capability_roles = ["discrepancy_reviewer", "data_exporter"]
        capability_grant_ids = None
        allow_classical_capability = current_user.has_role(
            "discrepancy_reviewer", "data_exporter"
        )
        if regrade_creator_mode:
            capability_roles = ["data_manager"]
            capability_grant_ids = list(
                authorized_manager_project_grant_ids(db, actor=current_user)
            )
            allow_classical_capability = current_user.has_role("data_manager")

        filters = {
            "project_id": project_id,
            "disease_id": disease_id,
            "lab_unit_id": lab_unit_id,
            "resident_grade": resident_grades,
            "resident2_grade": resident2_grades,
            "arbitrator_grade": arbitrator_grades,
            "regrade_grade": regrade_grades,
            "final_grade": final_grades,
            "has_ai_grade": has_ai_grade,
            "has_human_review": has_human_review,
            "has_review": has_review,
            "has_regrade": has_regrade,
            "has_arbitrator": has_arbitrator,
            "review_grade": review_grades,
            "has_consensus": has_consensus,
            "consensus_method": consensus_method,
            "resident_compare": resident_compare,
            "ai_model_id": ai_model_ids,
            "ai_grade": ai_grades,
            "ai_review_status": ai_review_statuses,
            "final_grade_basis": final_grade_basis,
            "allowed_lab_units": allowed_lab_units,
            "project_capability_role_names": capability_roles,
            "project_capability_grant_ids": capability_grant_ids,
            "project_capability_user_id": current_user.id,
            "allow_classical_capability": allow_classical_capability,
            "task_ids": list(review_queue.task_ids) if review_queue else [],
            "review_queue": review_queue_token or None,
        }

        mv_name, where_sql, params, selected_ai_model_id = build_discrepancy_filter_query(db, filters)
        if not mv_name:
            return render_template(
                "review/discrepancy_review.html",
                projects=projects,
                diseases=diseases,
                lab_units=lab_units,
                grade_options=grade_options,
                ai_models=ai_models,
                regrade_adjudicators=regrade_adjudicators,
                tasks=[],
                total_count=0,
                page=1,
                total_pages=0,
                has_prev=False,
                has_next=False,
                ai_review_status_labels=AI_REVIEW_STATUS_FILTER_LABELS,
                filters=filters,
                page_title=page_title,
                regrade_creator_mode=regrade_creator_mode,
                review_route=review_route,
            )

        base_query = f"""
            FROM {mv_name} v
            WHERE {where_sql}
        """

        # Total count for pagination
        count_sql = f"SELECT COUNT(*) {base_query}"
        total_count = db.execute(text(count_sql), params).scalar() or 0

        # Pagination setup
        page = request.args.get("page", 1, type=int)
        per_page = 50
        offset = (page - 1) * per_page

        order_sql = (
            "array_position(:task_ids, v.task_id)"
            if review_queue is not None
            else "v.task_id DESC"
        )
        data_sql = f"""
            SELECT
                v.task_id,
                v.task_state,
                v.task_lab_unit_id,
                v.lab_unit_name,
                v.hospital_name,
                v.encounter_file_uuid,
                v.direct_image_uuid,
                v.image_uuid,
                v.disease_name,
                v.has_consensus,
                v.consensus_type,
                v.final_grade_name,
                {sql_final_grade_expression(final_grade_basis)} AS final_impression,
                v.resident_grade_name,
                v.resident_comment,
                v.resident_selected_features_json,
                v.resident2_grade_name,
                v.resident2_comment,
                v.resident2_selected_features_json,
                v.arbitrator_grade_name,
                v.arbitrator_comment,
                v.arbitrator_selected_features_json,
                v.review_grade_name,
                v.review_comment,
                v.review_selected_features_json,
                v.regrade_adj_grade_name,
                v.regrade_adj_comment,
                v.regrade_adj_selected_features_json,
                v.ai_models_json
            {base_query}
            ORDER BY {order_sql}
            LIMIT :limit OFFSET :offset
        """
        params.update({"limit": per_page, "offset": offset})

        rows = db.execute(text(data_sql), params).fetchall()

        processed_tasks = []
        queue_ids = [row.task_id for row in rows]

        queue_len = len(queue_ids)
        for idx, row in enumerate(rows):
            grades_by_role = _build_grades_from_row(row, selected_ai_model_id)
            next_task_id = queue_ids[idx + 1] if idx + 1 < queue_len else None
            next_after_task_id = queue_ids[idx + 2] if idx + 2 < queue_len else None
            task_data = {
                "id": row.task_id,
                "state": row.task_state,
                "disease_name": row.disease_name,
                "lab_unit_name": row.lab_unit_name,
                "hospital_name": row.hospital_name,
                "encounter_file_uuid": row.encounter_file_uuid,
                "direct_image_uuid": row.direct_image_uuid or row.image_uuid,
                "grades": grades_by_role,
                "consensus": None,
                "final_impression": row.final_impression,
                "final_basis": derive_final_grade_source(
                    final_grade_basis,
                    resident_grade=row.resident_grade_name,
                    resident2_grade=row.resident2_grade_name,
                    arbitrator_grade=row.arbitrator_grade_name,
                    regrade_adj_grade=row.regrade_adj_grade_name,
                ),
                "next_task_id": next_task_id,
                "next_after_task_id": next_after_task_id,
            }
            if row.has_consensus:
                task_data["consensus"] = {
                    "id": None,
                    "impression": row.final_grade_name,
                    "method": row.consensus_type,
                }
            processed_tasks.append(task_data)

        total_pages = (total_count + per_page - 1) // per_page
        has_prev = page > 1
        has_next = page < total_pages

        template_name = (
            "review/_discrepancy_results.html"
            if request.headers.get("HX-Request") == "true"
            else "review/discrepancy_review.html"
        )
        return render_template(
            template_name,
            projects=projects,
            diseases=diseases,
            lab_units=lab_units,
            grade_options=grade_options,
            ai_models=ai_models,
            regrade_adjudicators=regrade_adjudicators,
            tasks=processed_tasks,
            total_count=total_count,
            page=page,
            total_pages=total_pages,
            has_prev=has_prev,
            has_next=has_next,
            ai_review_status_labels=AI_REVIEW_STATUS_FILTER_LABELS,
            filters={
                "project_id": project_id,
                "disease_id": disease_id,
                "lab_unit_id": lab_unit_id,
                "resident_grade": resident_grades,
                "resident2_grade": resident2_grades,
                "arbitrator_grade": arbitrator_grades,
                "final_grade": final_grades,
                "has_ai_grade": has_ai_grade,
                "has_human_review": has_human_review,
                "has_review": has_review,
                "has_regrade": has_regrade,
                "has_arbitrator": has_arbitrator,
                "review_grade": review_grades,
                "regrade_grade": regrade_grades,
                "has_consensus": has_consensus,
                "consensus_method": consensus_method,
                "resident_compare": resident_compare,
                "ai_model_id": ai_model_ids,
                "ai_grade": ai_grades,
                "ai_review_status": ai_review_statuses,
                "final_grade_basis": final_grade_basis,
                "task_ids": list(review_queue.task_ids) if review_queue else [],
                "review_queue": review_queue_token or None,
            },
            page_title=page_title,
            regrade_creator_mode=regrade_creator_mode,
            review_route=review_route,
        )


@bp.route("/discrepancy-review", methods=["GET"])
@login_required
def discrepancy_review():
    """Render the live discrepancy queue from the current MV snapshot.

    This is intentionally not response-cached. Reviewers mutate task review
    state through Save & Close / Save & Next, and a rendered response cache can
    outlive the disease materialized-view snapshot that produced it.
    """
    return render_discrepancy_review()


@bp.route("/discrepancy-export", methods=["POST"])
@bp.route(
    "/discrepancy-export-pii",
    methods=["POST"],
    endpoint="discrepancy_export_pii",
)
@login_required
def discrepancy_export():
    pii_action = request.endpoint == "review.discrepancy_export_pii"
    if pii_action:
        reauth_response = require_recent_reauthentication()
        if reauth_response is not None:
            return reauth_response
    with get_db_session() as db:
        review_queue = None
        review_queue_token = (request.form.get("review_queue") or "").strip()
        if review_queue_token:
            try:
                review_queue = load_review_queue(
                    db, user=current_user, token=review_queue_token
                )
            except ReviewQueueError:
                abort(404)
        if pii_action:
            allowed_lab_unit_ids = {
                row.id
                for row in db.execute(
                    identifier_release_lab_units(db, select(LabUnit), current_user)
                ).scalars().unique().all()
            }
        else:
            allowed_lab_unit_ids = capability_lab_unit_ids(
                db,
                user=current_user,
                roles=EXPORT_ROLES,
            )

        project_id = request.form.get("project_id", type=int)
        if project_id is not None:
            allowed_lab_unit_ids = set(allowed_lab_unit_ids).intersection(
                authorized_export_project_lab_unit_ids(
                    db,
                    actor=current_user,
                    project_id=project_id,
                    include_identifiers=pii_action,
                )
            )

        if not allowed_lab_unit_ids:
            from flask import flash, redirect, url_for
            flash("No lab units available for export.", "error")
            return redirect(url_for("review.discrepancy_review"))

        disease_id = request.form.get("disease_id", type=int)
        if not disease_id:
            from flask import flash, redirect, url_for
            flash("Disease selection is required for export.", "error")
            return redirect(url_for("review.discrepancy_review", **request.args))

        lab_unit_id = request.form.get("lab_unit_id", type=int)
        if lab_unit_id and lab_unit_id not in allowed_lab_unit_ids:
            from flask import flash, redirect, url_for
            flash("You are not allowed to export for this lab unit.", "error")
            return redirect(url_for("review.discrepancy_review", **request.args))
            
        # ... (ai_review_statuses extraction) ...
        ai_review_statuses = [
            status
            for status in request.form.getlist("ai_review_status")
            if status in AI_REVIEW_STATUS_FILTER_LABELS
        ]
        final_grade_basis = normalize_final_grade_basis(request.form.get("final_grade_basis"))
        # ... (rest of filtering logic) ...

        include_original_filename = pii_action
        skip_image_zips = request.form.get("skip_image_zips") == "1"

        filters = {
            "project_id": project_id,
            "disease_id": disease_id,
            "lab_unit_id": lab_unit_id,
            "resident_grade": request.form.getlist("resident_grade"),
            "resident2_grade": request.form.getlist("resident2_grade"),
            "arbitrator_grade": request.form.getlist("arbitrator_grade"),
            "regrade_grade": request.form.getlist("regrade_grade"),
            "final_grade": request.form.getlist("final_grade"),
            "has_ai_grade": request.form.get("has_ai_grade", type=str),
            "has_human_review": request.form.get("has_human_review", type=str),
            "has_review": request.form.get("has_review", type=str),
            "has_regrade": request.form.get("has_regrade", type=str),
            "has_arbitrator": request.form.get("has_arbitrator", type=str),
            "review_grade": request.form.getlist("review_grade"),
            "has_consensus": request.form.get("has_consensus", type=str),
            "consensus_method": request.form.get("consensus_method", type=str),
            "resident_compare": request.form.get("resident_compare", type=str),
            "ai_model_id": request.form.getlist("ai_model_id"),
            "ai_grade": request.form.getlist("ai_grade"),
            "ai_review_status": ai_review_statuses,
            "final_grade_basis": final_grade_basis,
            "allowed_lab_units": list(allowed_lab_unit_ids),
            "project_capability_role_names": ["pii_exporter"] if pii_action else ["data_exporter"],
            "project_capability_user_id": current_user.id,
            "project_capability_grant_ids": sorted(
                authorized_export_project_grant_ids(
                    db, actor=current_user, include_identifiers=pii_action
                )
            ),
            "task_ids": list(review_queue.task_ids) if review_queue else [],
            "allow_classical_capability": (
                current_user.has_role("admin")
                if pii_action
                else current_user.has_role("data_manager", "data_exporter")
            ),
            "authorization_action": "pii_export" if pii_action else "ordinary_export",
            "include_original_filename": include_original_filename,
            "skip_image_zips": skip_image_zips,
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

@bp.route("/discrepancy-export/<job_token>/<path:filename>", methods=["GET"])
@login_required
def discrepancy_export_download(job_token: str, filename: str):
    """Serve generated export artifacts (Excel or zip) for authorized users."""
    with Session() as db:
        job = db.query(Job).filter(Job.token == job_token, Job.upload_type == "discrepancy_export").first()
        if not job:
            abort(404)
        if job.status != "done" or job.uploader_user_id != current_user.id:
            abort(404)
        filters_path = (EXPORT_DIR / job_token / "filters.json").resolve()
        scope_path = (EXPORT_DIR / job_token / ARTIFACT_SCOPE_FILENAME).resolve()
        try:
            requested_filters = json.loads(filters_path.read_text(encoding="utf-8"))
            scope_manifest = json.loads(scope_path.read_text(encoding="utf-8"))
            if not reauthorize_discrepancy_artifact(
                db,
                current_user,
                requested_filters,
                scope_manifest.get("task_ids", ()),
            ):
                abort(404)
        except (OSError, ValueError, PermissionError):
            abort(404)

    export_dir = (EXPORT_DIR / job_token).resolve()
    target = (export_dir / filename).resolve()
    # startswith would accept a sibling directory sharing the token as a
    # prefix; relative_to is the real containment test.
    try:
        target.relative_to(export_dir)
    except ValueError:
        abort(404)
    if not target.is_file():
        abort(404)

    return send_file(target, as_attachment=True)

def get_disease_grading_id_by_impression(db: Session, impression: str) -> int | None:
    """Helper function to get disease grading ID by impression."""
    from models import DiseaseGrading
    grading = db.query(DiseaseGrading).filter(DiseaseGrading.impression == impression).first()
    return grading.id if grading else None


def _parse_json_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return value
    return value


def _parse_ai_models(value: Any) -> Dict[str, Dict[str, Any]]:
    parsed = _parse_json_value(value)
    if isinstance(parsed, dict):
        return parsed
    return {}


def _pick_ai_model(ai_models: Dict[str, Dict[str, Any]], selected_ai_model_id: Optional[int]) -> Optional[Dict[str, Any]]:
    if not ai_models:
        return None
    if selected_ai_model_id is not None:
        return ai_models.get(str(selected_ai_model_id))
    sorted_keys = sorted(ai_models.keys(), key=lambda k: int(k) if str(k).isdigit() else k)
    return ai_models.get(sorted_keys[0]) if sorted_keys else None


def _build_grades_from_row(row: Any, selected_ai_model_id: Optional[int]) -> Dict[str, Dict[str, Any]]:
    grades: Dict[str, Dict[str, Any]] = {}

    def _add_role(role: str, grade_name: Any, comment: Any, features: Any) -> None:
        if grade_name is None and comment is None and features is None:
            return
        grades[role] = {
            "impression": grade_name,
            "comment": comment,
            "selected_features": _parse_json_value(features),
        }

    _add_role("resident", row.resident_grade_name, row.resident_comment, row.resident_selected_features_json)
    _add_role("resident2", row.resident2_grade_name, row.resident2_comment, row.resident2_selected_features_json)
    _add_role("arbitrator", row.arbitrator_grade_name, row.arbitrator_comment, row.arbitrator_selected_features_json)
    _add_role("review", row.review_grade_name, row.review_comment, row.review_selected_features_json)
    _add_role("regrade_adj", row.regrade_adj_grade_name, row.regrade_adj_comment, row.regrade_adj_selected_features_json)

    ai_models = _parse_ai_models(row.ai_models_json)
    if ai_models:
        selected = _pick_ai_model(ai_models, selected_ai_model_id)
        all_statuses = [
            model.get("ai_review_status")
            for model in ai_models.values()
            if model.get("ai_review_status")
        ]
        all_comments = [
            model.get("ai_review_comment")
            for model in ai_models.values()
            if model.get("ai_review_comment")
        ]
        if selected:
            grades["ai"] = {
                "impression": selected.get("ai_grade_name"),
                "comment": selected.get("ai_comment"),
                "selected_features": _parse_json_value(selected.get("ai_selected_features")),
                "ai_model_name": selected.get("ai_model_name"),
                "ai_model_version": selected.get("ai_model_version"),
                "ai_probability": selected.get("ai_probability"),
            }
            if selected_ai_model_id is not None:
                if selected.get("ai_review_status"):
                    grades["ai"]["ai_review_statuses"] = [selected.get("ai_review_status")]
                if selected.get("ai_review_comment"):
                    grades["ai"]["ai_review_comments"] = [selected.get("ai_review_comment")]
            else:
                if all_statuses:
                    grades["ai"]["ai_review_statuses"] = all_statuses
                if all_comments:
                    grades["ai"]["ai_review_comments"] = all_comments
        else:
            if all_statuses or all_comments:
                grades["ai"] = {
                    "impression": None,
                    "comment": None,
                    "selected_features": None,
                    "ai_model_name": None,
                    "ai_model_version": None,
                    "ai_probability": None,
                    "ai_review_statuses": all_statuses,
                    "ai_review_comments": all_comments,
                }
    return grades
