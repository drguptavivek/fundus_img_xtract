from flask import render_template, request, flash, redirect, url_for
from flask_login import current_user
from sqlalchemy.orm import joinedload
import logging
import json
from json import JSONDecodeError
import re

from auth.roles import roles_required
from db_transaction_manager import get_db_session
from models import GradingTask, LabUnit, Grade, DiseaseGrading, GradingsFeatures, Consensus
from utils.upload_eligibility import get_user_lab_unit_ids
from utils.taskUtils import get_task_detail
from utils.dualGradingEligibility import get_user_eligibility_for_task
from utils.masterUtils import fetch_active_disease_gradings
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


@bp.route("/reviewTaskDetails/<int:task_id>", methods=["GET", "POST"])
@roles_required("admin", "local_admin", "data_manager", "optometrist")
def review_task_details(task_id: int):
    """View details for a specific task, scoped to user's eligible lab units."""
    with get_db_session() as db:
        # Get user's eligible lab units
        user_lab_unit_ids = get_user_lab_unit_ids(current_user.id)
        
        # First verify the task exists and is in a lab unit the user has access to
        task = (
            db.query(GradingTask)
            .join(LabUnit)
            .filter(GradingTask.id == task_id)
            .filter(GradingTask.lab_unit_id.in_(list(user_lab_unit_ids)))
            .options(
                joinedload(GradingTask.disease),
                joinedload(GradingTask.lab_unit),
                joinedload(GradingTask.encounter_file),
                joinedload(GradingTask.direct_image)  # Add direct image information
            )
            .first()
        )
        
        if not task:
            from flask import abort
            abort(404, description="Task not found or access denied")
        
        # Use the utility function to get comprehensive task details
        task_details = get_task_detail(db, task_id)
        
        if not task_details:
            from flask import abort
            abort(404, description="Task not found")
        
        # Check if user can review this task (has Resident2 or Arbitrator permissions)
        can_review = (
            get_user_eligibility_for_task(db, current_user.id, task_id, 'resident2') or
            get_user_eligibility_for_task(db, current_user.id, task_id, 'arbitrator')
        )
        
        # Get existing review grade if any
        existing_review_grade = None
        if can_review:
            existing_review_grade = db.query(Grade).filter(
                Grade.task_id == task_id,
                Grade.grader_user_id == current_user.id,
                Grade.role_slot == 'review'
            ).first()

        existing_selected_features = _parse_selected_features(
            existing_review_grade.selected_features_json if existing_review_grade else None
        )

        ai_grades = (
            db.query(Grade)
            .filter(Grade.task_id == task_id, Grade.role_slot == "ai")
            .options(joinedload(Grade.ai_model), joinedload(Grade.label))
            .all()
        )

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

        ai_grade_meta: dict[int, dict[str, object]] = {
            entry["id"]: entry for entry in ai_grades_for_display if isinstance(entry.get("id"), int)
        }

        # Handle POST request for submitting review grade
        if request.method == 'POST' and can_review:
            grading_id = request.form.get('grading_id', type=int)
            comment = request.form.get('comment', '')
            raw_selected_features = request.form.getlist('selected_features')
            selected_feature_ids: list[int] = []
            for raw_feature in raw_selected_features:
                if raw_feature is None or raw_feature == "":
                    continue
                try:
                    selected_feature_ids.append(int(raw_feature))
                except (TypeError, ValueError):
                    flash('Invalid feature selection submitted.', 'error')
                    return redirect(url_for('review.review_task_details', task_id=task_id))

            unique_feature_ids: list[int] = []
            seen_feature_ids: set[int] = set()
            for feature_id in selected_feature_ids:
                if feature_id not in seen_feature_ids:
                    unique_feature_ids.append(feature_id)
                    seen_feature_ids.add(feature_id)

            selected_features_json: str | None = None

            if not grading_id:
                flash('Please select a grade', 'error')
                return redirect(url_for('review.review_task_details', task_id=task_id))

            # Get the disease grading
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
                return redirect(url_for('review.review_task_details', task_id=task_id))

            if unique_feature_ids:
                available_features = (
                    db.query(GradingsFeatures)
                    .filter(GradingsFeatures.disease_grading_id == grading_id)
                    .all()
                )
                features_by_id = {feature.id: feature for feature in available_features}
                invalid_features = [fid for fid in unique_feature_ids if fid not in features_by_id]
                if invalid_features:
                    flash('One or more selected features are not valid for the chosen grade.', 'error')
                    return redirect(url_for('review.review_task_details', task_id=task_id))

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
            
            # Create or update review grade
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

            allowed_ai_statuses = set(AI_REVIEW_STATUS_LABELS.keys())
            for ai_grade in ai_grades:
                status_field = f"ai_review_status_{ai_grade.id}"
                comment_field = f"ai_review_comment_{ai_grade.id}"
                submitted_status = (request.form.get(status_field) or "").strip().lower() or None
                submitted_comment = (request.form.get(comment_field) or "").strip() or None

                if submitted_status and submitted_status not in allowed_ai_statuses:
                    flash('Invalid AI review selection submitted.', 'error')
                    return redirect(url_for('review.review_task_details', task_id=task_id))

                if submitted_status is None and submitted_comment is None:
                    continue

                ai_grade.ai_review_status = submitted_status
                ai_grade.ai_review_comment = submitted_comment
                ai_grade.ai_reviewed_by_user_id = current_user.id
                ai_grade.ai_reviewed_at = datetime.now(timezone.utc)

                ai_feedback_logs.append(
                    f"AI grade {ai_grade.id} status={submitted_status or 'none'} model={ai_grade.ai_model_name or (ai_grade.ai_model.name if ai_grade.ai_model else 'unknown')}"
                )

            if ai_feedback_logs:
                grades_logger.info(
                    "AI review feedback [user_id: %s] [task_id: %s] %s",
                    current_user.id,
                    task_id,
                    "; ".join(ai_feedback_logs),
                )

            db.commit()
            flash('Review grade submitted successfully', 'success')
            return redirect(url_for('review.review_task_details', task_id=task_id))
        
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

        existing_consensus = db.query(Consensus).filter(Consensus.task_id == task_id).first()

        # Determine which image object to use for the viewer
        image_object = task.encounter_file if task.encounter_file else task.direct_image

        # Render template within the same session to avoid detached instance errors
        return render_template(
            "review/task_detail_review.html",
            task=task_details,
            original_task=task,  # For additional properties not in summary
            image_object=image_object,
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
        )
