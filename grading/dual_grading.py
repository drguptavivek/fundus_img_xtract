from flask import render_template, request, redirect, url_for, flash, jsonify, current_app, make_response
from flask_login import current_user
from sqlalchemy import and_, or_
from sqlalchemy.orm import selectinload
import random
import logging
import os
from datetime import datetime, timedelta, timezone

from auth.roles import roles_required
from models import Session, GradingTask, Grade, Consensus, DiseaseGrading, Disease, UserDiseaseUnitRole, User, Role
from services.taskCreationServices import ensure_task as svc_ensure_task
from utils.dualGradingGetNextTasks import get_next_eligible_resident_task_atomic, get_next_eligible_faculty_task_atomic, get_next_eligible_arbitrator_task_atomic, get_next_eligible_resident_task, get_next_eligible_faculty_task, get_next_eligible_arbitrator_task, _has_user_graded_task_2weeks
from utils.dualGradingEligibility import check_arbitration_eligibility, get_user_eligibility_for_task
from utils.dualGradingFetchDetailUtils import fetch_grade_with_related_data, fetch_task_with_related_data, fetch_existing_grade_for_user
from utils.dualGradingEligibility import check_arbitration_eligibility
from utils.masterUtils import fetch_active_disease_gradings
from utils.dualGradingConsensusUtils import create_or_update_consensus, update_task_state_based_on_grades
from utils.dualGradingRevisionUtils import is_user_eligible_for_revision, is_arbitrator_eligible_for_revision, check_revision_eligibility_by_task_state, is_arbitrator_revision_allowed
from utils.dualGradingStuckTaskCleanup import mark_task_started, cleanup_task_tracker
from utils.notifications import send_notification_to_admins
from db_transaction_manager import transaction_scope
from utils.getNextIntraRaterTask import get_next_intra_rater_task



grades_logger = logging.getLogger("grades")


def register_routes(bp):
    """Register dual grading routes with the blueprint."""
    bp.add_url_rule("/task/<int:task_id>/<string:slot_type>", view_func=dual_grading_task, methods=["GET"])
    bp.add_url_rule("/task/submit", view_func=dual_grading_submit, methods=["POST"])
    bp.add_url_rule("/revise/<int:grade_id>", view_func=revise_grading, methods=["GET"])


@roles_required("resident", "ophthalmologist", "admin")
def revise_grading(grade_id: int):
    """Allow a user to revise their previous grading."""
    # Validate input
    if not grade_id or not isinstance(grade_id, int) or grade_id <= 0:
        flash("Invalid grade ID.", "danger")
        return redirect(url_for("grading.index"))
        
    with transaction_scope() as db:
        try:
            # Fetch the grade with related data using utility function
            grade = fetch_grade_with_related_data(db, grade_id)
            
            if not grade:
                flash("Grade not found.", "danger")
                return redirect(url_for("grading.index"))
            
            # Check if the user is the original grader
            if grade.grader_user_id != current_user.id:
                flash("You are not authorized to revise this grade.", "danger")
                return redirect(url_for("grading.index"))
            
            # Get the task
            task = grade.task
            
            # Check if user is eligible for revision using utility function
            eligibility_result = is_user_eligible_for_revision(db, current_user.id, task.id, grade.role_slot, grade)
            
            if not eligibility_result["eligible"]:
                flash(eligibility_result["message"], "danger")
                return redirect(url_for("grading.index"))
            
            # For revision, we need to verify they still have the appropriate role
            # For resident grading, allow both resident and ophthalmologist roles
            slot_type = grade.role_slot
            user_has_role = False
            if slot_type == 'resident':
                user_has_role = current_user.has_role('resident') or current_user.has_role('ophthalmologist')
            elif slot_type in ['faculty', 'arbitrator']:
                user_has_role = current_user.has_role('ophthalmologist')
            
            if not user_has_role:
                flash(f"You no longer have the required role ({slot_type}) to revise this grade.", "danger")
                return redirect(url_for("grading.index"))
            
            # Check if this is an arbitrator revising their recent grade on a final task
            is_arbitrator_revising_recent = eligibility_result.get("is_recent", False) and task.state == 'final'
            
            # Fetch disease gradings for this disease using utility function
            disease_gradings = fetch_active_disease_gradings(db, task.disease_id)
            
            # Check if disease_gradings are missing or invalid
            if not disease_gradings:
                flash("Error: No disease gradings available for this task. Please contact the system administrator.", "danger")
                # Send notification to admin about the missing disease gradings
                send_notification_to_admins(
                    title="Missing Disease Gradings in Task",
                    message=f"Task ID {task.id} does not have associated disease gradings. Please investigate and resolve this issue.",
                    notification_type="error"
                )
                return redirect(url_for("grading.index"))
            
            # Create a dictionary mapping grading IDs to their guidelines
            grading_guidelines = {grading.id: grading.guidelines for grading in disease_gradings}
            
            # Determine image URL
            image_uuid = None
            if task.encounter_file:
                image_uuid = task.encounter_file.uuid
            elif task.direct_image:
                image_uuid = task.direct_image.uuid
            
            # Check if image_uuid is None and handle it appropriately
            if image_uuid is None:
                flash("Warning: No image associated with this task. Please contact the system administrator.", "warning")
                # Send notification to admin about the missing image
                send_notification_to_admins(
                    title="Missing Image in Task",
                    message=f"Task ID {task.id} does not have an associated image. Please investigate and resolve this issue.",
                    notification_type="warning"
                )
                
            # Use the existing grade as the existing_grade parameter
            existing_grade = grade

            response = make_response(render_template(
                "grading/dual_grading_task.html",
                task=task,
                disease_gradings=disease_gradings,
                grading_guidelines=grading_guidelines,
                current_slot=slot_type,
                existing_grade=existing_grade,
                image_uuid=image_uuid,
                grades=task.grades,
                existing_grade_in_header=True,
                is_arbitrator_revising_recent=is_arbitrator_revising_recent,
                current_user_id=getattr(current_user, "id", None)
            ))
            
            # Prevent caching of this page
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, private'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
            
            return response
        except Exception as e:
            grades_logger.exception("Failed to load revision task: %s", e)
            flash("Failed to load revision task.", "danger")
            return redirect(url_for("grading.index"))


@roles_required("resident", "ophthalmologist", "admin")
def dual_grading_task(task_id: int, slot_type: str):
    """Display a task for dual grading."""
    from flask import session as flask_session
    
    with transaction_scope() as db:
        try:
            # Fetch the task with related data using utility function
            task = fetch_task_with_related_data(db, task_id)
            
            if not task:
                flash("Error: Task not found. Please contact the system administrator.", "danger")
                # Send notification to admin about the missing task
                send_notification_to_admins(
                    title="Missing Task Access Attempt",
                    message=f"User {current_user.id} attempted to access non-existent task ID {task_id}. Please investigate and resolve this issue.",
                    notification_type="error"
                )
                return redirect(url_for("grading.index"))
            
            # Validate slot_type
            if slot_type not in ['resident', 'faculty', 'arbitrator']:
                flash("Invalid slot type.", "danger")
                return redirect(url_for("grading.index"))
            
            # Check task state validity for the requested slot at assignment time
            state_validity = True
            if slot_type == 'resident':
                # Resident should only be assigned to 'pending' tasks
                if task.state not in ['pending']:
                    flash(f"Task is no longer available for resident grading (current state: {task.state}).", "danger")
                    state_validity = False
            elif slot_type == 'faculty':
                # Faculty should only be assigned to 'resident_done' tasks
                if task.state not in ['resident_done']:
                    flash(f"Task is no longer available for faculty grading (current state: {task.state}).", "danger")
                    state_validity = False
            elif slot_type == 'arbitrator':
                # Arbitrator should only be assigned to 'arbitration' tasks, or 'final' for recent revisions
                if task.state not in ['arbitration', 'final']:
                    flash(f"Task is no longer available for arbitration (current state: {task.state}).", "danger")
                    state_validity = False
            
            if not state_validity:
                return redirect(url_for("grading.index"))
            
            # Check if user is eligible for the specified slot
            if not get_user_eligibility_for_task(db, current_user.id, task_id, slot_type):
                flash(f"You are not eligible to grade this task as {slot_type}.", "danger")
                return redirect(url_for("grading.index"))
            
            # Check if the slot is available for this task state using utility function
            is_available, message = check_revision_eligibility_by_task_state(task.state, slot_type)
            
            # Special handling for arbitrator in final state (revision case)
            if slot_type == 'arbitrator' and task.state == 'final':
                # Check if this user is the arbitrator who made the decision and if it was recent
                arbitrator_eligibility = is_arbitrator_eligible_for_revision(db, current_user.id, task_id, task)
                if arbitrator_eligibility["eligible"]:
                    is_available = True
                    message = "Eligible for revision"
                else:
                    is_available = False
                    message = arbitrator_eligibility["message"]
                    
            if not is_available:
                flash(message, "danger")
                return redirect(url_for("grading.index"))
            
            # Fetch disease gradings for this disease using utility function
            disease_gradings = fetch_active_disease_gradings(db, task.disease_id)
            
            # Check if disease_gradings are missing or invalid
            if not disease_gradings:
                flash("Error: No disease gradings available for this task. Please contact the system administrator.", "danger")
                # Send notification to admin about the missing disease gradings
                send_notification_to_admins(
                    title="Missing Disease Gradings in Task",
                    message=f"Task ID {task_id} does not have associated disease gradings. Please investigate and resolve this issue.",
                    notification_type="error"
                )
                return redirect(url_for("grading.index"))
            
            # Create a dictionary mapping grading IDs to their guidelines
            grading_guidelines = {grading.id: grading.guidelines for grading in disease_gradings}
            
            # Determine image URL
            image_uuid = None
            if task.encounter_file:
                image_uuid = task.encounter_file.uuid
            elif task.direct_image:
                image_uuid = task.direct_image.uuid
            
            # Check if image_uuid is None and handle it appropriately
            if image_uuid is None:
                flash("Warning: No image associated with this task. Please contact the system administrator.", "warning")
                # Send notification to admin about the missing image
                send_notification_to_admins(
                    title="Missing Image in Task",
                    message=f"Task ID {task_id} does not have an associated image. Please investigate and resolve this issue.",
                    notification_type="warning"
                )
                
            # Fetch existing grade for this user and slot (for review purposes) using utility function
            existing_grade = fetch_existing_grade_for_user(db, task_id, current_user.id, slot_type)
            
            # If this is an arbitration task, fetch resident and faculty grades to show to the arbitrator
            resident_grade = None
            faculty_grade = None
            if slot_type == 'arbitrator' and task.state == 'arbitration':
                for grade in task.grades:
                    if grade.role_slot == 'resident':
                        resident_grade = grade
                    elif grade.role_slot == 'faculty':
                        faculty_grade = grade
        
            # Check if this is an arbitrator revising their recent grade on a final task
            is_arbitrator_revising_recent = False
            if slot_type == 'arbitrator' and task.state == 'final' and existing_grade:
                arbitrator_eligibility = is_user_eligible_for_revision(db, current_user.id, task_id, slot_type, existing_grade)
                is_arbitrator_revising_recent = arbitrator_eligibility.get("is_recent", False)

            # Check if this is a revision by checking if the user already has a grade for this task and slot
            existing_grade_for_slot = fetch_existing_grade_for_user(db, task_id, current_user.id, slot_type)
            is_revision = existing_grade_for_slot is not None
            
            # Store the start time in the session for fallback
            start_time_key = f"grading_start_time_{task_id}_{slot_type}"
            start_time_iso = datetime.now(timezone.utc).isoformat()
            flask_session[start_time_key] = start_time_iso
            
            # Mark that the user has started working on this task for stuck task tracking
            # but only if this is not a revision (i.e., user doesn't already have a grade for this slot)
            if not is_revision:
                mark_task_started(task_id, current_user.id, slot_type)
            
            # Pass grades for display in the template
            grades = task.grades
                
            return render_template(
                "grading/dual_grading_task.html",
                task=task,
                disease_gradings=disease_gradings,
                grading_guidelines=grading_guidelines,
                current_slot=slot_type,
                existing_grade=existing_grade,
                image_uuid=image_uuid,
                grades=grades,
                existing_grade_in_header=True,
                resident_grade=resident_grade,
                faculty_grade=faculty_grade,
                is_arbitrator_revising_recent=is_arbitrator_revising_recent,
                start_time_iso=start_time_iso,  # Pass start time to template as hidden field
                current_user_id=getattr(current_user, "id", None)
            )
        except Exception as e:
            grades_logger.exception("Failed to load grading task: %s", e)
            flash("Failed to load grading task.", "danger")
            return redirect(url_for("grading.index"))

 
@roles_required("resident", "ophthalmologist", "admin")
def dual_grading_submit():
    """Submit a grade for a task."""
    from flask import session as flask_session
    
    task_id = request.form.get("task_id", type=int)
    slot = (request.form.get("slot") or "").strip().lower()
    label_id = request.form.get("label_id", type=int)
    comment = (request.form.get("comment") or "").strip() or None
    
    # Validate inputs
    if not task_id or not isinstance(task_id, int) or task_id <= 0:
        flash("Invalid task ID.", "danger")
        return redirect(url_for("grading.index"))
        
    if not label_id or not isinstance(label_id, int) or label_id <= 0:
        flash("Invalid label ID.", "danger")
        return redirect(url_for("grading.index"))
    
    if slot not in {"resident", "faculty", "arbitrator"}:
        flash("Invalid slot type.", "danger")
        return redirect(url_for("grading.index"))
    
    from db_transaction_manager import transaction_scope
    with transaction_scope() as db:
        try:
            # Use utility function to fetch the task with related data
            task = fetch_task_with_related_data(db, task_id)
            if not task:
                flash("Error: Task not found. Please contact the system administrator.", "danger")
                # Send notification to admin about the missing task
                send_notification_to_admins(
                    title="Missing Task Access Attempt",
                    message=f"User {current_user.id} attempted to access non-existent task ID {task_id}. Please investigate and resolve this issue.",
                    notification_type="error"
                )
                return redirect(url_for("grading.index"))
            
            # Check if this is an arbitrator's revision within 6 hours to allow modifying finalized tasks
            arbitrator_revision_allowed = False
            if slot == "arbitrator":
                # Use utility function to check if arbitrator revision is allowed
                from utils.dualGradingRevisionUtils import is_arbitrator_revision_allowed
                revision_check = is_arbitrator_revision_allowed(db, current_user.id, task_id, slot)
                arbitrator_revision_allowed = revision_check["allowed"]
            
            if task.state == "final" and not arbitrator_revision_allowed:
                flash("This task is already finalized.", "danger")
                return redirect(url_for("grading.dual_grading_task", task_id=task_id, slot_type=slot))
            
            # Check task state validity at submission time to prevent race conditions 
            # by revalidating the state that was expected when the task was assigned
            state_validity = True
            if slot == 'resident':
                # Resident should only be grading 'pending' or 'resident_done' tasks (for revisions)
                if task.state not in ['pending', 'resident_done']:
                    flash(f"Task state has changed and is no longer available for resident grading (current state: {task.state}).", "danger")
                    state_validity = False
            elif slot == 'faculty':
                # Faculty should only be grading 'resident_done', 'faculty_done', or 'arbitration' tasks (for revisions)
                if task.state not in ['resident_done', 'faculty_done', 'arbitration']:
                    flash(f"Task state has changed and is no longer available for faculty grading (current state: {task.state}).", "danger")
                    state_validity = False
            elif slot == 'arbitrator':
                # Arbitrator should only be grading 'arbitration' or 'final' tasks (for eligible revisions)
                if task.state not in ['arbitration', 'final']:
                    flash(f"Task state has changed and is no longer available for arbitration (current state: {task.state}).", "danger")
                    state_validity = False
                    
            if not state_validity:
                return redirect(url_for("grading.index"))
            
            # Eligibility check
            if not get_user_eligibility_for_task(db, current_user.id, task_id, slot):
                flash("You are not eligible to grade this task for the selected role.", "danger")
                return redirect(url_for("grading.dual_grading_task", task_id=task_id, slot_type=slot))
            
            # Additional role validation for arbitrator
            if slot == "arbitrator":
                # Check if user has the required role for arbitration
                if not current_user.has_role('ophthalmologist'):
                    flash("You don't have permission to grade as arbitrator.", "danger")
                    return redirect(url_for("grading.index"))
                
                # Check arbitration eligibility using utility function
                eligibility = check_arbitration_eligibility(db, current_user.id, task.disease_id, task.lab_unit_id)
                
                if not eligibility:
                    flash("You are not eligible to arbitrate for this task.", "danger")
                    return redirect(url_for("grading.dual_grading_task", task_id=task_id, slot_type=slot))
            
            # Arbitrator exclusion: cannot be prior resident/faculty grader within 2 weeks
            # However, if this is a revision of an existing arbitrator grade by the same user, skip this check
            if slot == "arbitrator":
                # Check if this is a revision of an existing arbitrator grade by the same user
                existing_grade = fetch_existing_grade_for_user(db, task_id, current_user.id, slot)
                is_arbitrator_revision = (
                    existing_grade and 
                    existing_grade.role_slot == "arbitrator" and 
                    existing_grade.grader_user_id == current_user.id
                )
                
                # Only apply the exclusion check if this is not an arbitrator revising their own grade
                if not is_arbitrator_revision and _has_user_graded_task_2weeks(db, current_user.id, task_id):
                    flash("You cannot arbitrate a task you've graded as resident or faculty within the last 2 weeks.", "danger")
                    return redirect(url_for("grading.dual_grading_task", task_id=task_id, slot_type=slot))
            
            # Validate label belongs to task.disease_id using utility function
            disease_gradings = fetch_active_disease_gradings(db, task.disease_id)
            if not disease_gradings:
                flash("Error: No disease gradings available for this task. Please contact the system administrator.", "danger")
                return redirect(url_for("grading.index"))

            label = next((dg for dg in disease_gradings if dg.id == label_id), None)
            if not label:
                flash("Invalid label.", "danger")
                return redirect(url_for("grading.dual_grading_task", task_id=task_id, slot_type=slot))
            
            # Fetch existing grade using utility function
            existing_grade = fetch_existing_grade_for_user(db, task_id, current_user.id, slot)
            had_existing_grade = existing_grade is not None

            # Capture previous values for logging (before updating)
            prev_grade_id = None
            prev_comment = None

            if had_existing_grade:
                prev_grade_id = existing_grade.disease_grading_id
                prev_comment = existing_grade.comment

            # Log grade submission (including revisions) using dedicated grades logger
            # Store in UTC for consistency
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            ip_address = request.environ.get('HTTP_X_REAL_IP', request.remote_addr)
            
            grade_type = "revision" if had_existing_grade else "new"
            grade_id = existing_grade.id if had_existing_grade and existing_grade else "N/A"
            
            # Create log message
            log_message = f"Grade submission [IP: {ip_address}] [user_id: {current_user.id}] [Task ID: {task_id}] [Slot Type: {slot}] [Disease ID: {task.disease_id}] [Grade: {label_id}] [Type: {grade_type}] [Grade ID: {grade_id}]"
            if comment:
                log_message += f" [Comments - {comment}]"
                
            # If this is a revision, also log the previous grade and comment
            if had_existing_grade and prev_grade_id is not None:
                prev_comment_display = prev_comment if prev_comment else "None"
                log_message += f" [Previous Grade: {prev_grade_id}] [Previous Comment: {prev_comment_display}]"
            
            # Log using dedicated grades logger
            grades_logger.info(log_message)
            
            # Calculate time taken
            time_taken = None
            start_time_key = f"grading_start_time_{task_id}_{slot}"
            
            # Try to get start time from form data first (to handle page refreshes)
            start_time_str = request.form.get("start_time_iso")
            
            # If not in form, try to get from session
            if not start_time_str:
                start_time_str = flask_session.get(start_time_key)
            
            if start_time_str:
                try:
                    start_time = datetime.fromisoformat(start_time_str)
                    # Handle timezone-naive datetimes by assuming they are UTC
                    if start_time.tzinfo is None:
                        start_time = start_time.replace(tzinfo=timezone.utc)
                    current_time = datetime.now(timezone.utc)
                    time_taken = int((current_time - start_time).total_seconds())
                    # Remove the start time from session as we've used it
                    flask_session.pop(start_time_key, None)
                except (ValueError, TypeError):
                    # If there's an error parsing the start time, just leave time_taken as None
                    pass
            
            if existing_grade:
                # Fetch the disease and grade information to populate denormalized fields
                disease_grading = db.query(DiseaseGrading).filter(DiseaseGrading.id == label_id).first()
                disease = None
                if disease_grading:
                    disease = db.query(Disease).filter(Disease.id == disease_grading.disease_id).first()
                
                existing_grade.disease_grading_id = label_id
                existing_grade.comment = comment
                existing_grade.time_taken = time_taken
                # Update denormalized fields as well
                existing_grade.disease_name = disease.name if disease else None
                existing_grade.grade_name = disease_grading.impression if disease_grading else None
                existing_grade.grade_description = disease_grading.guidelines if disease_grading else None
                db.add(existing_grade)
                db.flush()  # Ensure the ID is available
            else:
                # Fetch the disease and grade information to populate denormalized fields
                disease_grading = db.query(DiseaseGrading).filter(DiseaseGrading.id == label_id).first()
                disease = None
                if disease_grading:
                    disease = db.query(Disease).filter(Disease.id == disease_grading.disease_id).first()
                
                new_grade = Grade(
                    task_id=task.id,
                    grader_user_id=current_user.id,
                    role_slot=slot,
                    disease_grading_id=label_id,
                    comment=comment,
                    time_taken=time_taken,
                    disease_name=disease.name if disease else None,
                    grade_name=disease_grading.impression if disease_grading else None,
                    grade_description=disease_grading.guidelines if disease_grading else None
                )
                db.add(new_grade)
                db.flush()  # Ensure the ID is available
                existing_grade = new_grade  # So we can use existing_grade.id below

            # Update task state based on grades using utility function
            # Note: We need to call update_task_state_based_on_grades with just the task_id, not the whole task object
            from utils.dualGradingConsensusUtils import update_task_state_based_on_grades
            update_task_state_based_on_grades(task.id, db)
            
            # Create or update consensus if applicable based on the grades
            # This should be called after task state is updated to ensure proper consensus creation
            from utils.dualGradingConsensusUtils import create_or_update_consensus
            create_or_update_consensus(task.id, db)
            
            # Clean up the task tracker record if this is not a revision
            # For revisions, no tracker was created in the first place, so no need to cleanup
            # We'll pass the db session to the cleanup function to include it in the same transaction
            if not had_existing_grade:
                from utils.dualGradingStuckTaskCleanup import cleanup_task_tracker
                cleanup_task_tracker(task_id, current_user.id, slot, db)
            
            # Store disease_id for later use
            disease_id = task.disease_id
            
            # Check if we should go to the next task
            action = (request.form.get("action") or "").strip().lower()
            if action == "save_next":
                # Since we're closing the current session to get the next task,
                # we need to commit our changes first
                db.commit()
                try:
                    intra_task = get_next_intra_rater_task(current_user.id, disease_id)
                    if intra_task and random.random() < 0.5:
                        flash("Grade submitted successfully.", "success")
                        return redirect(
                            url_for(
                                "grading.intra_rater_task",
                                task_id=intra_task.id,
                                resume_slot=slot,
                                resume_disease_id=disease_id,
                            )
                        )

                    # Try to find the next eligible task with a new session
                    next_task = None
                    if slot == "resident":
                        next_task = get_next_eligible_resident_task_atomic(current_user.id, disease_id)
                    elif slot == "faculty":
                        next_task = get_next_eligible_faculty_task_atomic(current_user.id, disease_id)
                    elif slot == "arbitrator":
                        next_task = get_next_eligible_arbitrator_task_atomic(current_user.id, disease_id)
                    
                    # Handle the result
                    if next_task is None:
                        flash("Grade submitted successfully.", "success")
                        flash("No more tasks available.", "info")
                        return redirect(url_for("grading.index"))
                    elif isinstance(next_task, str):
                        # It's a helpful message
                        flash("Grade submitted successfully.", "success")
                        flash(next_task, "info")
                        return redirect(url_for("grading.index"))
                    else:
                        # It's a GradingTask object
                        flash("Grade submitted successfully.", "success")
                        return redirect(url_for("grading.dual_grading_task", task_id=next_task.id, slot_type=slot))
                except Exception as e:
                    grades_logger.exception("Failed to find next task: %s", e)
                    flash("Grade submitted successfully, but failed to navigate to next task.", "warning")
                    return redirect(url_for("grading.index"))
            else:
                # For save_close or any other action, just show success and redirect to index
                flash("Grade submitted successfully.", "success")
                return redirect(url_for("grading.index"))
        except Exception as e:
            grades_logger.exception("Failed to submit grade: %s", e)
            flash("Failed to submit grade.", "danger")
            raise  # Re-raise the exception so the transaction is rolled back
