from flask import render_template, request, flash, redirect, url_for
from flask_login import current_user
from sqlalchemy import or_
from sqlalchemy.orm import joinedload
import logging
import json
from json import JSONDecodeError
import re
from urllib.parse import parse_qs, urlsplit

from auth.roles import roles_required
from db_transaction_manager import get_db_session
from models import GradingTask, LabUnit, Grade, DiseaseGrading, GradingsFeatures, Consensus, ImageMetadata

from utils.hospital_scoping import apply_scoping
from utils.taskUtils import get_task_detail
from utils.security_middleware import is_safe_url
from utils.dualGradingEligibility import get_user_eligibility_for_task
from utils.masterUtils import fetch_active_disease_gradings
from utils.dualGradingFetchDetailUtils import get_user_gradings_with_details
from utils.review_navigation import get_next_review_tasks
from utils.cache_invalidation import invalidate_discrepancy_review_cache
from datetime import datetime, timezone
from . import bp

# Initialize grades logger for review grade submissions
grades_logger = logging.getLogger("grades")

AI_REVIEW_STATUS_LABELS: dict[str, str] = {
    "ok": "OK",
    "minor_miss": "Minor miss",
    "major_miss": "Major miss",
}


def _parse_selected_features(selected_features_json: str | None) -> list[dict[str, object] | str]:
    """Return a best-effort parsed list of previously selected features."""
    if not selected_features_json:
        return []

    try:
        parsed = json.loads(selected_features_json)
        if isinstance(parsed, list):
            return parsed
    except JSONDecodeError:
        grades_logger.warning("Failed to parse stored review selected_features_json", exc_info=True)

    return []


def _extract_ai_probability(comment: str | None) -> str | None:
    """Pull AI probability substring from a stored comment, if present."""
    if not comment:
        return None
    match = re.search(r"AI probability:\s*([0-9.]+)", comment, flags=re.IGNORECASE)
    return match.group(1) if match else None


def _apply_ai_influence_comment(comment: str | None, ai_influence: str | None) -> str | None:
    if not ai_influence:
        return comment
    normalized = ai_influence.strip().lower()
    if normalized not in {"yes", "no"}:
        return comment
    tag = f"AI influence: {'yes' if normalized == 'yes' else 'no'}"
    if not comment:
        return tag
    lines = [line for line in comment.splitlines() if line.strip()]
    updated = []
    replaced = False
    for line in lines:
        if line.lower().startswith("ai influence:"):
            updated.append(tag)
            replaced = True
        else:
            updated.append(line)
    if not replaced:
        updated.append(tag)
    return "\n".join(updated)


def _submitted_action(default: str = "save") -> str:
    for action in reversed(request.form.getlist("action")):
        action = (action or "").strip()
        if action:
            return action
    return default


def _return_to_args(return_to: str | None) -> dict[str, list[str]]:
    if not return_to:
        return {}
    try:
        return parse_qs(urlsplit(return_to).query, keep_blank_values=True)
    except ValueError:
        return {}


def _arg_or_return_to(
    name: str,
    return_to_args: dict[str, list[str]],
    *,
    type_=str,
):
    value = request.args.get(name, type=type_)
    if value is not None:
        return value
    values = return_to_args.get(name, [])
    if not values:
        return None
    raw_value = values[-1]
    if raw_value == "":
        return ""
    try:
        return type_(raw_value)
    except (TypeError, ValueError):
        return None


def _arglist_or_return_to(name: str, return_to_args: dict[str, list[str]]) -> list[str]:
    values = request.args.getlist(name)
    if values:
        return values
    return return_to_args.get(name, [])


@bp.route("/reviewTaskDetails/<int:task_id>", methods=["GET", "POST"])
@roles_required("discrepancy_reviewer")
def review_task_details(task_id: int):
    """View details for a specific task, scoped to user's eligible lab units."""
    with get_db_session() as db:
        # Build query for the task
        query = (
            db.query(GradingTask)
            .filter(GradingTask.id == task_id)
            .options(
                joinedload(GradingTask.disease),
                joinedload(GradingTask.lab_unit),
                joinedload(GradingTask.encounter_file),
                joinedload(GradingTask.direct_image)
            )
        )
        # Apply hospital scoping to ensure task is within user's access
        query = apply_scoping(query, GradingTask, current_user, "view")
        task = query.first()
        
        if not task:
            from flask import abort
            abort(404, description="Task not found or access denied")
        
        # Use the utility function to get comprehensive task details
        task_details = get_task_detail(db, task_id)
        
        if not task_details:
            from flask import abort
            abort(404, description="Task not found")
        
        allowed_methods = {"match", "adjudication", "regrade", "task_review"}
        existing_consensus = db.query(Consensus).filter(Consensus.task_id == task_id).first()
        # Allow review only for discrepancy reviewers and eligible consensus methods
        can_review = current_user.has_role("discrepancy_reviewer") and (
            existing_consensus is not None and existing_consensus.method in allowed_methods
        )
        
        # Get allowed lab units for navigation
        lu_query = db.query(LabUnit)
        lu_query = apply_scoping(lu_query, LabUnit, current_user, "view")
        user_lab_unit_ids = [lu.id for lu in lu_query.all()]
        
        # The grades table permits one review row per task/user. Use the
        # current user's row for edits so we do not insert a duplicate.
        existing_review_grade = (
            db.query(Grade)
            .filter(
                Grade.task_id == task_id,
                Grade.grader_user_id == current_user.id,
                Grade.role_slot == "review",
            )
            .order_by(Grade.updated_at.desc().nullslast(), Grade.id.desc())
            .first()
        )

        existing_selected_features = _parse_selected_features(
            existing_review_grade.selected_features_json if existing_review_grade else None
        )

        return_to = request.args.get("return_to")
        return_to_query_args = _return_to_args(return_to)
        ai_model_id_filter = _arg_or_return_to("ai_model_id", return_to_query_args, type_=int)

        lab_unit_id_filter = _arg_or_return_to("lab_unit_id", return_to_query_args, type_=int)
        has_consensus = _arg_or_return_to("has_consensus", return_to_query_args)
        has_review = _arg_or_return_to("has_review", return_to_query_args)
        has_ai_grade = _arg_or_return_to("has_ai_grade", return_to_query_args)
        resident_grades = _arglist_or_return_to("resident_grade", return_to_query_args)
        resident2_grades = _arglist_or_return_to("resident2_grade", return_to_query_args)
        arbitrator_grades = _arglist_or_return_to("arbitrator_grade", return_to_query_args)
        regrade_grades = _arglist_or_return_to("regrade_grade", return_to_query_args)
        review_grades = _arglist_or_return_to("review_grade", return_to_query_args)
        final_grades = _arglist_or_return_to("final_grade", return_to_query_args)
        ai_grades = _arglist_or_return_to("ai_grade", return_to_query_args)
        ai_review_statuses = _arglist_or_return_to("ai_review_status", return_to_query_args)
        final_grade_basis = _arg_or_return_to("final_grade_basis", return_to_query_args)
        resident_compare = _arg_or_return_to("resident_compare", return_to_query_args)
        consensus_method = _arg_or_return_to("consensus_method", return_to_query_args)
        has_regrade = _arg_or_return_to("has_regrade", return_to_query_args)
        has_arbitrator = _arg_or_return_to("has_arbitrator", return_to_query_args)

        navigation_params: dict[str, object] = {
            "disease_id": task.disease_id,
            "lab_unit_id": lab_unit_id_filter,
            "has_consensus": has_consensus,
            "consensus_method": consensus_method,
            "has_review": has_review,
            "has_regrade": has_regrade,
            "has_arbitrator": has_arbitrator,
            "has_ai_grade": has_ai_grade,
            "final_grade_basis": final_grade_basis,
            "resident_compare": resident_compare,
        }
        if ai_model_id_filter:
            navigation_params["ai_model_id"] = ai_model_id_filter
        for key, values in {
            "resident_grade": resident_grades,
            "resident2_grade": resident2_grades,
            "arbitrator_grade": arbitrator_grades,
            "regrade_grade": regrade_grades,
            "review_grade": review_grades,
            "final_grade": final_grades,
            "ai_grade": ai_grades,
            "ai_review_status": ai_review_statuses,
        }.items():
            if values:
                navigation_params[key] = values

        nav_result = get_next_review_tasks(
            db,
            current_task_id=task_id,
            disease_id=task.disease_id,
            lab_unit_ids=list(user_lab_unit_ids),
            lab_unit_id=lab_unit_id_filter,
            has_consensus=has_consensus,
            consensus_method=consensus_method,
            has_review=has_review,
            has_regrade=has_regrade,
            has_arbitrator=has_arbitrator,
            has_ai_grade=has_ai_grade,
            ai_model_id=ai_model_id_filter,
            final_grade_basis=final_grade_basis,
            ai_grades=ai_grades or None,
            ai_review_statuses=ai_review_statuses or None,
            resident_grades=resident_grades or None,
            resident2_grades=resident2_grades or None,
            arbitrator_grades=arbitrator_grades or None,
            regrade_grades=regrade_grades or None,
            review_grades=review_grades or None,
            final_grades=final_grades or None,
            limit=50,
        )
        next_task_id = nav_result.get("next_task_id")

        redirect_kwargs: dict[str, object] = {"task_id": task_id}
        for key, value in navigation_params.items():
            if value not in (None, "", []):
                redirect_kwargs[key] = value
        ai_grades_query = (
            db.query(Grade)
            .filter(Grade.task_id == task_id, Grade.role_slot == "ai")
            .options(joinedload(Grade.ai_model), joinedload(Grade.label))
        )
        if ai_model_id_filter:
            ai_grades_query = ai_grades_query.filter(Grade.ai_model_id == ai_model_id_filter)
            redirect_kwargs["ai_model_id"] = ai_model_id_filter
        if return_to:
            redirect_kwargs["return_to"] = return_to
        if next_task_id:
            redirect_kwargs["next_task_id"] = next_task_id
        ai_grades = ai_grades_query.all()

        ai_grades_for_display: list[dict[str, object]] = []
        for ai_grade in ai_grades:
            ai_grades_for_display.append(
                {
                    "id": ai_grade.id,
                    "impression": ai_grade.grade_name
                    or (ai_grade.label.impression if ai_grade.label else None),
                    "comment": ai_grade.comment,
                    "ai_model_name": ai_grade.ai_model_name
                    or (ai_grade.ai_model.name if ai_grade.ai_model else None),
                    "ai_model_version": ai_grade.ai_model_version
                    or (ai_grade.ai_model.version if ai_grade.ai_model else None),
                    "ai_probability": _extract_ai_probability(ai_grade.comment),
                    "review_status": ai_grade.ai_review_status,
                    "review_comment": ai_grade.ai_review_comment,
                }
            )
        ai_visible = bool(ai_grades_for_display)

        ai_grade_meta: dict[int, dict[str, object]] = {
            entry["id"]: entry for entry in ai_grades_for_display if isinstance(entry.get("id"), int)
        }

        # Handle POST request for submitting review grade
        if request.method == 'POST' and can_review:
            grading_id = request.form.get('grading_id', type=int)
            comment = request.form.get('comment', '')
            ai_influence = (request.form.get('ai_influence') or '').strip().lower()
            action = _submitted_action()
            form_next_task_id = request.form.get('next_task_id', type=int)
            target_next_task_id = form_next_task_id or next_task_id
            raw_selected_features = request.form.getlist('selected_features')
            effective_next_task_id = target_next_task_id or nav_result.get("next_task_id")
            next_redirect_params: dict[str, object] = {
                k: v for k, v in navigation_params.items() if v not in (None, "", [])
            }
            if ai_model_id_filter:
                next_redirect_params["ai_model_id"] = ai_model_id_filter
            if return_to:
                next_redirect_params["return_to"] = return_to

            grades_logger.info(
                "Review submit navigation context",
                extra={
                    "action": action,
                    "target_next_task_id": target_next_task_id,
                    "fallback_next_task_id": nav_result.get("next_task_id"),
                    "return_to": return_to,
                    "navigation_params": next_redirect_params,
                },
            )

            ai_feedback_payload: list[dict[str, object]] = []
            ai_feedback_present = False
            allowed_ai_statuses = set(AI_REVIEW_STATUS_LABELS.keys())
            for ai_grade in ai_grades:
                status_field = f"ai_review_status_{ai_grade.id}"
                comment_field = f"ai_review_comment_{ai_grade.id}"
                submitted_status = (request.form.get(status_field) or "").strip().lower() or None
                submitted_comment = (request.form.get(comment_field) or "").strip() or None

                if submitted_status and submitted_status not in allowed_ai_statuses:
                    flash('Invalid AI review selection submitted.', 'error')
                    return redirect(url_for('review.review_task_details', **redirect_kwargs))

                if submitted_status is None and submitted_comment is None:
                    continue

                ai_feedback_present = True
                ai_feedback_payload.append(
                    {
                        "grade_obj": ai_grade,
                        "status": submitted_status,
                        "comment": submitted_comment,
                    }
                )

            if action == "cancel_next":
                if return_to and is_safe_url(return_to) and effective_next_task_id:
                    return redirect(
                        url_for(
                            'review.review_task_details',
                            task_id=effective_next_task_id,
                            **next_redirect_params,
                        )
                    )
                if effective_next_task_id:
                    return redirect(
                        url_for(
                            'review.review_task_details',
                            task_id=effective_next_task_id,
                            **next_redirect_params,
                        )
                    )
                if return_to and is_safe_url(return_to):
                    return redirect(return_to)
                return redirect(url_for('review.discrepancy_review'))

            selected_feature_ids: list[int] = []
            for raw_feature in raw_selected_features:
                if raw_feature is None or raw_feature == "":
                    continue
                try:
                    selected_feature_ids.append(int(raw_feature))
                except (TypeError, ValueError):
                    flash('Invalid feature selection submitted.', 'error')
                    return redirect(url_for('review.review_task_details', **redirect_kwargs))

            unique_feature_ids: list[int] = []
            seen_feature_ids: set[int] = set()
            for feature_id in selected_feature_ids:
                if feature_id not in seen_feature_ids:
                    unique_feature_ids.append(feature_id)
                    seen_feature_ids.add(feature_id)

            selected_features_json: str | None = None

            if not grading_id and not ai_feedback_present:
                flash('Please select a grade', 'error')
                return redirect(url_for('review.review_task_details', **redirect_kwargs))

            if grading_id and ai_visible and ai_influence not in {"yes", "no"}:
                flash('Please specify whether the review was updated based on AI.', 'error')
                return redirect(url_for('review.review_task_details', **redirect_kwargs))

            # Get the disease grading
            disease_grading = None
            if grading_id:
                disease_grading = (
                    db.query(DiseaseGrading)
                    .filter(
                        DiseaseGrading.id == grading_id,
                        DiseaseGrading.disease_id == task.disease_id,
                        DiseaseGrading.is_active.is_(True),
                    )
                    .first()
                )
                
                if not disease_grading:
                    flash('Invalid grade selected', 'error')
                    return redirect(url_for('review.review_task_details', **redirect_kwargs))

            if grading_id and unique_feature_ids:
                available_features = (
                    db.query(GradingsFeatures)
                    .filter(GradingsFeatures.disease_grading_id == grading_id)
                    .all()
                )
                features_by_id = {feature.id: feature for feature in available_features}
                invalid_features = [fid for fid in unique_feature_ids if fid not in features_by_id]
                if invalid_features:
                    flash('One or more selected features are not valid for the chosen grade.', 'error')
                    return redirect(url_for('review.review_task_details', **redirect_kwargs))

                selected_feature_entities = sorted(
                    (features_by_id[fid] for fid in unique_feature_ids),
                    key=lambda feature: ((feature.sr_no or 0), feature.id),
                )

                selected_features_json = json.dumps(
                    [
                        {
                            "id": feature.id,
                            "label": feature.label,
                            "sr_no": feature.sr_no,
                        }
                        for feature in selected_feature_entities
                    ]
                )

            ip_address = request.environ.get('HTTP_X_REAL_IP', request.remote_addr)
            previous_consensus = db.query(Consensus).filter(Consensus.task_id == task_id).first()
            previous_consensus_method = previous_consensus.method if previous_consensus else None
            previous_consensus_grade_id = previous_consensus.final_disease_grading_id if previous_consensus else None

            # Determine if this is a revision
            is_revision = existing_review_grade is not None
            grade_type = "revision" if is_revision else "new"
            grade_id = existing_review_grade.id if existing_review_grade else "N/A"
            
            # Capture previous values for logging (before updating)
            prev_grade_id = None
            prev_comment = None
            
            if is_revision:
                prev_grade_id = existing_review_grade.disease_grading_id
                prev_comment = existing_review_grade.comment
            
            # Create log message
            log_message = f"Grade submission [IP: {ip_address}] [user_id: {current_user.id}] [Task ID: {task_id}] [Slot Type: review] [Disease ID: {task.disease_id}] [Grade: {grading_id}] [Type: {grade_type}] [Grade ID: {grade_id}]"
            if comment:
                log_message += f" [Comments - {comment}]"

            # If this is a revision, also log the previous grade and comment
            if is_revision and prev_grade_id is not None:
                prev_comment_display = prev_comment if prev_comment else "None"
                log_message += f" [Previous Grade: {prev_grade_id}] [Previous Comment: {prev_comment_display}]"

            ai_feedback_logs: list[str] = []

            # Log using dedicated grades logger
            grades_logger.info(log_message)
            
            comment = _apply_ai_influence_comment(comment, ai_influence) if grading_id else comment

            # Create or update review grade
            if grading_id and disease_grading:
                if existing_review_grade:
                    existing_review_grade.disease_grading_id = grading_id
                    existing_review_grade.comment = comment
                    existing_review_grade.grade_name = disease_grading.impression
                    existing_review_grade.disease_name = task.disease.name if task.disease else None
                    existing_review_grade.grade_description = disease_grading.guidelines
                    existing_review_grade.selected_features_json = selected_features_json
                    existing_review_grade.updated_at = datetime.now(timezone.utc)
                else:
                    new_review_grade = Grade(
                        task_id=task_id,
                        grader_user_id=current_user.id,
                        role_slot='review',
                        disease_grading_id=grading_id,
                        comment=comment,
                        grade_name=disease_grading.impression,
                        disease_name=task.disease.name if task.disease else None,
                        grade_description=disease_grading.guidelines,
                        selected_features_json=selected_features_json,
                        created_at=datetime.now(timezone.utc),
                        updated_at=datetime.now(timezone.utc)
                    )
                    db.add(new_review_grade)

                # If task already final, overwrite/create consensus with review grade
                if task.state == "final":
                    consensus_record = previous_consensus or Consensus(task_id=task_id)
                    consensus_record.final_disease_grading_id = grading_id
                    consensus_record.method = "task_review"
                    consensus_record.decided_by_user_id = current_user.id
                    consensus_record.decided_at = datetime.now(timezone.utc)
                    consensus_record.final_disease_name = task.disease.name if task.disease else None
                    consensus_record.final_grade_name = disease_grading.impression
                    consensus_record.final_grade_description = disease_grading.guidelines
                    db.add(consensus_record)
                    grades_logger.info(
                        "Consensus override via review [user_id: %s] [task_id: %s] [new_grade_id: %s] "
                        "[prev_method: %s] [prev_grade_id: %s]",
                        current_user.id,
                        task_id,
                        grading_id,
                        previous_consensus_method,
                        previous_consensus_grade_id,
                    )

            for payload in ai_feedback_payload:
                ai_grade_obj = payload["grade_obj"]
                ai_grade_obj.ai_review_status = payload["status"]
                ai_grade_obj.ai_review_comment = payload["comment"]
                ai_grade_obj.ai_reviewed_by_user_id = current_user.id
                ai_grade_obj.ai_reviewed_at = datetime.now(timezone.utc)

                ai_feedback_logs.append(
                    f"AI grade {ai_grade_obj.id} status={payload['status'] or 'none'} model={ai_grade_obj.ai_model_name or (ai_grade_obj.ai_model.name if ai_grade_obj.ai_model else 'unknown')}"
                )

            if ai_feedback_logs:
                grades_logger.info(
                    "AI review feedback [user_id: %s] [task_id: %s] %s",
                    current_user.id,
                    task_id,
                    "; ".join(ai_feedback_logs),
                )

            db.commit()
            invalidate_discrepancy_review_cache()
            success_message = 'Review grade submitted successfully' if grading_id else 'AI feedback submitted successfully'
            flash(success_message, 'success')
            if return_to and is_safe_url(return_to):
                if action in {"save_next", "cancel_next"} and effective_next_task_id:
                    return redirect(
                        url_for(
                            'review.review_task_details',
                            task_id=effective_next_task_id,
                            **next_redirect_params,
                        )
                    )
                return redirect(return_to)
            if action in {"save_next", "cancel_next"} and effective_next_task_id:
                return redirect(
                    url_for(
                        'review.review_task_details',
                        task_id=effective_next_task_id,
                        **next_redirect_params,
                    )
                )
            return redirect(url_for('review.discrepancy_review'))
        
        # Get available grades for the disease
        available_grades = fetch_active_disease_gradings(db, task.disease_id)

        grading_features: list[dict[str, object]] = []
        for grade in available_grades:
            sorted_features = sorted(
                grade.features or [],
                key=lambda feature: ((feature.sr_no or 0), feature.id),
            )
            grading_features.append(
                {
                    "id": grade.id,
                    "impression": grade.impression,
                    "display_order": grade.display_order,
                    "guidelines": grade.guidelines,
                    "features": [
                        {
                            "id": feature.id,
                            "sr_no": feature.sr_no,
                            "label": feature.label,
                        }
                        for feature in sorted_features
                    ],
                }
            )

        # Collect selected features for existing grader roles to display in UI
        role_feature_map: dict[str, list[dict[str, object] | str]] = {}
        grader_roles = ["resident", "resident2", "arbitrator"]
        existing_role_grades = (
            db.query(Grade)
            .filter(Grade.task_id == task_id, Grade.role_slot.in_(grader_roles))
            .all()
        )
        for role in grader_roles:
            grade_for_role = next((g for g in existing_role_grades if g.role_slot == role), None)
            role_feature_map[role] = _parse_selected_features(
                grade_for_role.selected_features_json if grade_for_role else None
            )

        # Determine which image object to use for the viewer
        image_object = task.encounter_file if task.encounter_file else task.direct_image
        image_metadata = None
        if image_object:
            image_metadata = (
                db.query(ImageMetadata)
                .filter(
                    ImageMetadata.image_uuid == image_object.uuid,
                    ImageMetadata.image_variant == "orig",
                )
                .first()
            )

        # Render template within the same session to avoid detached instance errors
        return render_template(
            "review/task_detail_review.html",
            task=task_details,
            original_task=task,  # For additional properties not in summary
            image_object=image_object,
            image_metadata=image_metadata,
            can_review=can_review,
            existing_review_grade=existing_review_grade,
            available_grades=available_grades,
            grading_features=grading_features,
            existing_selected_features=existing_selected_features,
            role_feature_map=role_feature_map,
            existing_consensus=existing_consensus,
            ai_grades=ai_grades_for_display,
            ai_review_status_labels=AI_REVIEW_STATUS_LABELS,
            ai_grade_meta=ai_grade_meta,
            ai_model_id_filter=ai_model_id_filter,
            return_to=return_to,
            next_task_id=next_task_id,
            task_detail_query_string=request.query_string.decode("utf-8"),
        )


@bp.route("/my-reviews")
@roles_required("admin", "local_admin", "data_manager", "optometrist")
def my_reviews():
    """List review grades submitted by the current user."""
    page = request.args.get("page", 1, type=int)
    per_page = 20
    filter_date = request.args.get("date")

    with get_db_session() as db:
        reviews, total_count = get_user_gradings_with_details(
            db,
            user_id=current_user.id,
            page=page,
            per_page=per_page,
            role_slot="review",
            filter_date=filter_date,
        )

        total_pages = (total_count + per_page - 1) // per_page
        has_prev = page > 1
        has_next = page < total_pages

        return render_template(
            "review/my_reviews.html",
            reviews=reviews,
            page=page,
            total_pages=total_pages,
            has_prev=has_prev,
            has_next=has_next,
            filter_date=filter_date,
        )


@bp.route("/my-reviews/viewer/<string:image_uuid>")
@roles_required("admin", "local_admin", "data_manager", "optometrist")
def my_reviews_viewer(image_uuid: str):
    """Serve the grading viewer card for a review image UUID."""
    with get_db_session() as db:
        query = (
            db.query(GradingTask)
            .filter(
                or_(
                    GradingTask.encounter_file.has(uuid=image_uuid),
                    GradingTask.direct_image.has(uuid=image_uuid),
                ),
            )
            .options(joinedload(GradingTask.encounter_file), joinedload(GradingTask.direct_image))
        )
        query = apply_scoping(query, GradingTask, current_user, "view")
        task = query.first()
        if not task:
            return ("Not found", 404)

        image_obj = task.encounter_file or task.direct_image
        return render_template("partials/_grading_card.html", image=image_obj, image_uuid=image_uuid)
