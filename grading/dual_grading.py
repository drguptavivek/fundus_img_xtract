from flask import render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import current_user
from sqlalchemy import and_, or_
from sqlalchemy.orm import selectinload
import random

from auth.roles import roles_required
from models import Session, GradingTask, Grade, Consensus, DiseaseGrading, Disease, UserDiseaseUnitRole
from services.taskCreationServices import ensure_task as svc_ensure_task
from utils.getNextDualGradingTasks import get_next_eligible_resident_task, get_next_eligible_faculty_task, get_next_eligible_arbitrator_task
from utils.dualGradingUtils import get_user_eligibility_for_task


@roles_required("resident", "ophthalmologist", "admin")
def revise_grading(grade_id: int):
    """Allow a user to revise their previous grading."""
    db = Session()
    try:
        # Fetch the grade with related data
        grade = db.query(Grade).options(
            selectinload(Grade.task).selectinload(GradingTask.disease),
            selectinload(Grade.task).selectinload(GradingTask.encounter_file),
            selectinload(Grade.task).selectinload(GradingTask.direct_image),
            selectinload(Grade.task).selectinload(GradingTask.consensus).selectinload(Consensus.decided_by),
            selectinload(Grade.task).selectinload(GradingTask.consensus).selectinload(Consensus.final_label),
            selectinload(Grade.task).selectinload(GradingTask.grades).selectinload(Grade.grader),
            selectinload(Grade.task).selectinload(GradingTask.grades).selectinload(Grade.label),
            selectinload(Grade.label)
        ).filter(Grade.id == grade_id).first()
        
        if not grade:
            flash("Grade not found.", "danger")
            return redirect(url_for("grading.index"))
        
        # Check if the user is the original grader
        if grade.grader_user_id != current_user.id:
            flash("You are not authorized to revise this grade.", "danger")
            return redirect(url_for("grading.index"))
        
        # Get the task
        task = grade.task
        
        # Check if the task is still in a state that allows revision
        if task.state == "final":
            flash("This task is finalized and cannot be revised.", "danger")
            return redirect(url_for("grading.index"))
        
        # Determine the slot type based on the existing grade
        slot_type = grade.role_slot
        
        # For revision, we bypass the normal eligibility check since the user has already been eligible
        # We just need to verify they still have the appropriate role
        user_has_role = False
        if slot_type == 'resident':
            user_has_role = current_user.has_role('resident')
        elif slot_type in ['faculty', 'arbitrator']:
            user_has_role = current_user.has_role('ophthalmologist')
        
        if not user_has_role:
            flash(f"You no longer have the required role ({slot_type}) to revise this grade.", "danger")
            return redirect(url_for("grading.index"))
        
        # For revision, we need to be more permissive with task state validation
        # since the user is just updating their existing grade
        # Note: We already checked for "final" state above, so we don't need to check it again here
        slot_valid = False
        if slot_type == 'resident':
            # Resident can revise their grade at any point before finalization
            slot_valid = True
        elif slot_type == 'faculty':
            # Faculty can revise their grade at any point before finalization
            slot_valid = True
        elif slot_type == 'arbitrator':
            # Arbitrator can revise if task is in arbitration state
            slot_valid = task.state == 'arbitration'
        
        if not slot_valid:
            flash(f"{slot_type.capitalize()} slot is not available for this task (task state: {task.state}).", "danger")
            return redirect(url_for("grading.index"))
        
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
            
        # Use the existing grade as the existing_grade parameter
        existing_grade = grade
            
        return render_template(
            "grading/dual_grading_task.html",
            task=task,
            disease_gradings=disease_gradings,
            current_slot=slot_type,
            existing_grade=existing_grade,
            image_uuid=image_uuid,
            grades=task.grades
        )
    finally:
        db.close()


@roles_required("resident", "ophthalmologist", "admin")
def dual_grading_task(task_id: int, slot_type: str):
    """Display a task for dual grading."""
    db = Session()
    try:
        # Fetch the task with related data
        task = db.query(GradingTask).options(
            selectinload(GradingTask.disease),
            selectinload(GradingTask.encounter_file),
            selectinload(GradingTask.direct_image),
            selectinload(GradingTask.consensus).selectinload(Consensus.decided_by),
            selectinload(GradingTask.consensus).selectinload(Consensus.final_label),
            selectinload(GradingTask.grades).selectinload(Grade.grader),
            selectinload(GradingTask.grades).selectinload(Grade.label)
        ).filter(GradingTask.id == task_id).first()
        
        if not task:
            flash("Task not found.", "danger")
            return redirect(url_for("grading.index"))
        
        # Validate slot_type
        if slot_type not in ['resident', 'faculty', 'arbitrator']:
            flash("Invalid slot type.", "danger")
            return redirect(url_for("grading.index"))
        
        # Check if user is eligible for the specified slot
        if not get_user_eligibility_for_task(current_user.id, task_id, slot_type):
            flash(f"You are not eligible to grade this task as {slot_type}.", "danger")
            return redirect(url_for("grading.index"))
        
        # Additional validation: Check if the slot is actually available for this task state
        if slot_type == 'resident' and task.state != 'pending':
            flash("Resident slot is not available for this task.", "danger")
            return redirect(url_for("grading.index"))
        elif slot_type == 'faculty' and task.state != 'resident_done':
            flash("Faculty slot is not available for this task.", "danger")
            return redirect(url_for("grading.index"))
        elif slot_type == 'arbitrator' and task.state != 'arbitration':
            flash("Arbitrator slot is not available for this task.", "danger")
            return redirect(url_for("grading.index"))
        
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
            
        # Fetch existing grade for this user and slot (for review purposes)
        existing_grade = db.query(Grade).filter(
            Grade.task_id == task_id,
            Grade.grader_user_id == current_user.id,
            Grade.role_slot == slot_type
        ).first()
        
        # Pass grades for display in the template
        grades = task.grades
            
        return render_template(
            "grading/dual_grading_task.html",
            task=task,
            disease_gradings=disease_gradings,
            current_slot=slot_type,
            existing_grade=existing_grade,
            image_uuid=image_uuid,
            grades=grades
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
        if not get_user_eligibility_for_task(current_user.id, task_id, slot):
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
            next_task = None
            if slot == "resident":
                next_task = get_next_eligible_resident_task(current_user.id, task.disease_id)
            elif slot == "faculty":
                next_task = get_next_eligible_faculty_task(current_user.id, task.disease_id)
            elif slot == "arbitrator":
                next_task = get_next_eligible_arbitrator_task(current_user.id, task.disease_id)
            
            # Handle the result
            if next_task is None:
                flash("No more tasks available.", "info")
            elif isinstance(next_task, str):
                # It's a helpful message
                flash(next_task, "info")
            else:
                # It's a GradingTask object
                return redirect(url_for("grading.dual_grading_task", task_id=next_task.id, slot_type=slot))
        
        db.close()
        return redirect(url_for("grading.dual_grading_task", task_id=task_id))
    except Exception as e:
        current_app.logger.exception("Failed to submit grade: %s", e)
        db.rollback()
        flash("Failed to submit grade.", "danger")
        db.close()
        return redirect(url_for("grading.dual_grading_task", task_id=task_id))