from flask import render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import current_user
from sqlalchemy import and_, or_
from sqlalchemy.orm import selectinload
import random

from auth.roles import roles_required
from models import Session, GradingTask, Grade, Consensus, DiseaseGrading, Disease, UserDiseaseUnitRole
from services.taskCreationServices import ensure_task as svc_ensure_task

def is_user_eligible_for_slot(user, task, slot):
    """
    Check if a user is eligible for a specific slot (resident/faculty/arbitrator) for a task.
    
    Args:
        user: The user to check
        task: The grading task
        slot: The slot to check ('resident', 'faculty', or 'arbitrator')
    
    Returns:
        bool: True if user is eligible, False otherwise
    """
    # Admins are eligible for all slots
    if user.has_role('admin'):
        return True
    
    if not task or not task.disease_id or not task.lab_unit_id:
        return False
    
    # Check global role requirements
    if slot == 'resident' and not user.has_role('resident'):
        return False
    elif slot in ('faculty', 'arbitrator') and not user.has_role('ophthalmologist'):
        return False
    
    # Check eligibility matrix
    with Session() as db:
        eligibility = db.query(UserDiseaseUnitRole).filter(
            UserDiseaseUnitRole.user_id == user.id,
            UserDiseaseUnitRole.disease_id == task.disease_id,
            UserDiseaseUnitRole.lab_unit_id == task.lab_unit_id,
            UserDiseaseUnitRole.active == True
        ).first()
        
        if not eligibility:
            return False
            
        # Check specific slot permissions
        if slot == 'resident' and not eligibility.can_grade_resident:
            return False
        elif slot == 'faculty' and not eligibility.can_grade_faculty:
            return False
        elif slot == 'arbitrator' and not eligibility.can_arbitrate:
            return False
            
        return True


@roles_required("resident", "ophthalmologist", "admin")
def dual_grading_task(task_id: int):
    """Display a task for dual grading."""
    db = Session()
    try:
        # Fetch the task with related data
        task = db.query(GradingTask).options(
            selectinload(GradingTask.disease),
            selectinload(GradingTask.encounter_file),
            selectinload(GradingTask.direct_image),
            selectinload(GradingTask.consensus)
        ).filter(GradingTask.id == task_id).first()
        
        if not task:
            flash("Task not found.", "danger")
            return redirect(url_for("grading.index"))
        
        # Check if user is eligible for any slot
        user_roles = []
        if current_user.has_role('admin'):
            # Admins can access all tasks
            user_roles = ['resident', 'faculty', 'arbitrator']
        else:
            if is_user_eligible_for_slot(current_user, task, 'resident'):
                user_roles.append('resident')
            if is_user_eligible_for_slot(current_user, task, 'faculty'):
                user_roles.append('faculty')
            if is_user_eligible_for_slot(current_user, task, 'arbitrator'):
                user_roles.append('arbitrator')
            
            if not user_roles:
                flash("You are not eligible to grade this task.", "danger")
                return redirect(url_for("grading.index"))
        
        # Fetch existing grades for this task
        grades = db.query(Grade).filter(Grade.task_id == task_id).all()
        
        # Check if user has already graded this task
        user_grade = None
        for grade in grades:
            if grade.grader_user_id == current_user.id:
                user_grade = grade
                break
        
        # Determine which slots are available
        available_slots = []
        resident_grade = next((g for g in grades if g.role_slot == 'resident'), None)
        faculty_grade = next((g for g in grades if g.role_slot == 'faculty'), None)
        
        # Admins can access all slots regardless of existing grades or task state
        if current_user.has_role('admin'):
            if not resident_grade:
                available_slots.append('resident')
            if not faculty_grade:
                available_slots.append('faculty')
            if task.state == 'arbitration':
                available_slots.append('arbitrator')
        else:
            if 'resident' in user_roles and not resident_grade:
                available_slots.append('resident')
            if 'faculty' in user_roles and not faculty_grade:
                available_slots.append('faculty')
            if 'arbitrator' in user_roles and task.state == 'arbitration':
                available_slots.append('arbitrator')
            
        # Fetch disease gradings for this disease
        disease_gradings = db.query(DiseaseGrading).filter(
            DiseaseGrading.disease_id == task.disease_id,
            DiseaseGrading.is_active == True
        ).order_by(DiseaseGrading.display_order).all()
        
        # Determine image URL
        image_uuid = None
        if task.encounter_file:
            image_uuid = task.encounter_file.uuid
        elif task.direct_image:
            image_uuid = task.direct_image.uuid
            
        return render_template(
            "grading/dual_grading_task.html",
            task=task,
            disease_gradings=disease_gradings,
            grades=grades,
            user_grade=user_grade,
            user_roles=user_roles,
            available_slots=available_slots,
            image_uuid=image_uuid
        )
    finally:
        db.close()


@roles_required("resident", "ophthalmologist", "admin")
def dual_grading_submit():
    """Submit a grade for a task."""
    task_id = request.form.get("task_id", type=int)
    slot = (request.form.get("slot") or "").strip().lower()
    label_id = request.form.get("label_id", type=int)
    comment = (request.form.get("comment") or "").strip() or None
    
    if not task_id or slot not in {"resident", "faculty", "arbitrator"} or not label_id:
        flash("Invalid request.", "danger")
        return redirect(url_for("grading.index"))
    
    db = Session()
    try:
        task = db.query(GradingTask).filter(GradingTask.id == task_id).first()
        if not task:
            flash("Task not found.", "danger")
            return redirect(url_for("grading.index"))
        
        if task.state == "final":
            flash("This task is already finalized.", "danger")
            return redirect(url_for("grading.dual_grading_task", task_id=task_id))
        
        # Eligibility check
        if not current_user.has_role('admin') and not is_user_eligible_for_slot(current_user, task, slot):
            flash("You are not eligible to grade this task for the selected role.", "danger")
            return redirect(url_for("grading.dual_grading_task", task_id=task_id))
        
        # Arbitrator exclusion: cannot be prior resident/faculty grader
        # Admins are exempt from this restriction
        if slot == "arbitrator" and not current_user.has_role('admin'):
            existing_grade = db.query(Grade).filter(
                Grade.task_id == task.id,
                Grade.grader_user_id == current_user.id,
                Grade.role_slot.in_(["resident", "faculty"])
            ).first()
            
            if existing_grade:
                flash("You cannot arbitrate a task you've already graded as resident or faculty.", "danger")
                return redirect(url_for("grading.dual_grading_task", task_id=task_id))
        
        # Validate label belongs to task.disease_id
        label = db.query(DiseaseGrading).filter(
            DiseaseGrading.id == label_id,
            DiseaseGrading.disease_id == task.disease_id
        ).first()
        if not label:
            flash("Invalid label.", "danger")
            return redirect(url_for("grading.dual_grading_task", task_id=task_id))
        
        # Upsert grade
        existing_grade = db.query(Grade).filter(
            Grade.task_id == task.id,
            Grade.grader_user_id == current_user.id,
            Grade.role_slot == slot
        ).first()
        
        if existing_grade:
            existing_grade.disease_grading_id = label_id
            existing_grade.comment = comment
            db.add(existing_grade)
        else:
            new_grade = Grade(
                task_id=task.id,
                grader_user_id=current_user.id,
                role_slot=slot,
                disease_grading_id=label_id,
                comment=comment
            )
            db.add(new_grade)
        
        # Update task state based on grades
        # Fetch all grades for this task
        all_grades = db.query(Grade).filter(Grade.task_id == task.id).all()
        
        # Check if we have resident and faculty grades
        resident_grade = next((g for g in all_grades if g.role_slot == "resident"), None)
        faculty_grade = next((g for g in all_grades if g.role_slot == "faculty"), None)
        
        # Determine new state
        if slot == "arbitrator":
            # Arbitrator has graded - finalize task
            task.state = "final"
            # Create consensus
            consensus = Consensus(
                task_id=task.id,
                final_disease_grading_id=label_id,
                method="arbitration",
                decided_by_user_id=current_user.id
            )
            db.add(consensus)
        elif resident_grade and faculty_grade:
            # Both grades submitted, check for match
            if resident_grade.disease_grading_id == faculty_grade.disease_grading_id:
                # Match - finalize task
                task.state = "final"
                # Create consensus
                consensus = Consensus(
                    task_id=task.id,
                    final_disease_grading_id=resident_grade.disease_grading_id,
                    method="match",
                    decided_by_user_id=None  # System decision
                )
                db.add(consensus)
            else:
                # No match - go to arbitration
                task.state = "arbitration"
        elif resident_grade and not faculty_grade:
            task.state = "resident_done"
        elif faculty_grade and not resident_grade:
            task.state = "faculty_done"
        else:
            task.state = "pending"
        
        db.commit()
        flash("Grade submitted successfully.", "success")
        
        # Check if we should go to the next task
        action = (request.form.get("action") or "").strip().lower()
        if action == "save_next":
            # Close the current session first
            db.close()
            # Try to find the next eligible task with a new session
            next_task = _get_next_eligible_task(None, slot)
            if next_task:
                return redirect(url_for("grading.dual_grading_task", task_id=next_task.id))
            else:
                flash("No more tasks available.", "info")
        
        db.close()
        return redirect(url_for("grading.dual_grading_task", task_id=task_id))
    except Exception as e:
        current_app.logger.exception("Failed to submit grade: %s", e)
        db.rollback()
        flash("Failed to submit grade.", "danger")
        db.close()
        return redirect(url_for("grading.dual_grading_task", task_id=task_id))


def _get_next_eligible_task(db, slot):
    """
    Get the next eligible task for the current user and slot.
    
    Args:
        db: Database session (if None, a new session will be created)
        slot: The slot to get tasks for ('resident', 'faculty', 'arbitrator')
    
    Returns:
        GradingTask or None
    """
    # Get user's lab unit IDs
    user_lab_unit_ids = [lu.id for lu in current_user.lab_units] if hasattr(current_user, 'lab_units') else []
    if not user_lab_unit_ids:
        return None
    
    # Create a new session if needed
    close_db = False
    if db is None:
        db = Session()
        close_db = True
    
    try:
        # Build query for next task
        query = db.query(GradingTask).filter(
            GradingTask.lab_unit_id.in_(user_lab_unit_ids)
        )
        
        # Filter by slot-specific states
        if slot == "arbitrator":
            # Arbitrators only see arbitration tasks
            query = query.filter(GradingTask.state == "arbitration")
        else:
            # Residents and faculty see pending tasks or tasks where their slot hasn't graded yet
            query = query.filter(GradingTask.state.in_(["pending", "resident_done", "faculty_done"]))
        
        # Exclude tasks already graded by this user for this slot
        graded_task_ids = db.query(Grade.task_id).filter(
            Grade.grader_user_id == current_user.id,
            Grade.role_slot == slot
        ).all()
        graded_task_ids = [t[0] for t in graded_task_ids]
        
        if graded_task_ids:
            query = query.filter(~GradingTask.id.in_(graded_task_ids))
        
        # Order by priority and created_at
        # Prioritize tasks with one grade already submitted
        query = query.order_by(
            (GradingTask.state == "resident_done").desc(),
            (GradingTask.state == "faculty_done").desc(),
            GradingTask.created_at.asc()
        )
        
        return query.first()
    finally:
        if close_db:
            db.close()