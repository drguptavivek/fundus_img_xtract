from flask import render_template, request, jsonify, flash, redirect, url_for
from flask_login import current_user
from sqlalchemy.orm import joinedload

from auth.roles import roles_required
from db_transaction_manager import get_db_session
from models import GradingTask, LabUnit, Grade, DiseaseGrading, Session as DBSession
from utils.upload_eligibility import get_user_lab_unit_ids
from utils.taskUtils import get_task_detail
from utils.dualGradingEligibility import get_user_eligibility_for_task
from datetime import datetime, timezone
from . import bp


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
        
        # Check if user can review this task (has Faculty or Arbitrator permissions)
        can_review = (
            get_user_eligibility_for_task(db, current_user.id, task_id, 'faculty') or
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
        
        # Handle POST request for submitting review grade
        if request.method == 'POST' and can_review:
            grading_id = request.form.get('grading_id')
            comment = request.form.get('comment', '')
            
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
            
            # Create or update review grade
            if existing_review_grade:
                existing_review_grade.disease_grading_id = grading_id
                existing_review_grade.comment = comment
                existing_review_grade.grade_name = disease_grading.impression
                existing_review_grade.disease_name = task.disease.name if task.disease else None
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
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc)
                )
                db.add(new_review_grade)
            
            db.commit()
            flash('Review grade submitted successfully', 'success')
            return redirect(url_for('review.review_task_details', task_id=task_id))
        
        # Get available grades for the disease
        available_grades = db.query(DiseaseGrading).filter(
            DiseaseGrading.disease_id == task.disease_id,
            DiseaseGrading.is_active == True
        ).order_by(DiseaseGrading.display_order).all()
        
        # Determine which image object to use for the viewer
        image_object = task.encounter_file if task.encounter_file else task.direct_image

        return render_template(
            "review/task_detail_review.html",
            task=task_details,
            original_task=task,  # For additional properties not in summary
            image_object=image_object,
            can_review=can_review,
            existing_review_grade=existing_review_grade,
            available_grades=available_grades
        )