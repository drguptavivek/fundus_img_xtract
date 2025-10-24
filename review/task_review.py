from flask import render_template, request, flash, redirect, url_for
from flask_login import current_user
from sqlalchemy.orm import joinedload
import logging
import json
from json import JSONDecodeError

from auth.roles import roles_required
from db_transaction_manager import get_db_session
from models import GradingTask, LabUnit, Grade, DiseaseGrading, GradingsFeatures, Session as DBSession
from utils.upload_eligibility import get_user_lab_unit_ids
from utils.taskUtils import get_task_detail
from utils.dualGradingEligibility import get_user_eligibility_for_task
from utils.masterUtils import fetch_active_disease_gradings
from datetime import datetime, timezone
from . import bp

# Initialize grades logger for review grade submissions
grades_logger = logging.getLogger("grades")


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


@bp.route("/reviewTaskDetails/<int:task_id>", methods=["GET", "POST"])
@roles_required("admin", "data_manager", "optometrist")
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
            disease_grading = db.query(DiseaseGrading).filter(
                DiseaseGrading.id == grading_id,
                DiseaseGrading.disease_id == task.disease_id
            ).first()
            
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

            # Log review grade submission (including revisions) using dedicated grades logger
            # Store in UTC for consistency
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            ip_address = request.environ.get('HTTP_X_REAL_IP', request.remote_addr)
            
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

        # Determine which image object to use for the viewer
        image_object = task.encounter_file if task.encounter_file else task.direct_image

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
        )
