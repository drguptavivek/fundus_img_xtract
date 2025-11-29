'''
Features dsiplay for dual graded added. 
'''
from flask import render_template, request, redirect, url_for, flash, jsonify, current_app, make_response
from flask_login import current_user
from sqlalchemy import and_, or_
import random
import logging
import os
import json
from json import JSONDecodeError
from datetime import datetime, timedelta, timezone
 
from auth.roles import roles_required
from models import (
    Session,
    GradingTask,
    Grade,
    Consensus,
    DiseaseGrading,
    Disease,
    GradingsFeatures,
    UserDiseaseUnitRole,
    User,
    Role,
)
from services.taskCreationServices import ensure_task as svc_ensure_task
from utils.dualGradingGetNextTasks import (
    get_next_eligible_resident_task_atomic,
    get_next_eligible_resident2_task_atomic,
    get_next_eligible_arbitrator_task_atomic,
    get_next_eligible_resident_task,
    get_next_eligible_resident2_task,
    get_next_eligible_arbitrator_task,
    _has_user_graded_task_2weeks,
)
from utils.dualGradingEligibility import (
    check_arbitration_eligibility,
    get_user_eligibility_for_task,
    has_user_graded_task,
)

from utils.dualGradingFetchDetailUtils import (
    fetch_grade_with_related_data,
    fetch_task_with_related_data,
    fetch_task_with_related_data_by_uuid,
    fetch_existing_grade_for_user,
)
from utils.dualGradingEligibility import check_arbitration_eligibility
from utils.masterUtils import fetch_active_disease_gradings
from utils.dualGradingConsensusUtils import create_or_update_consensus, update_task_state_based_on_grades
from utils.dualGradingRevisionUtils import is_user_eligible_for_revision, is_arbitrator_eligible_for_revision, check_revision_eligibility_by_task_state, is_arbitrator_revision_allowed
from utils.dualGradingStuckTaskCleanup import mark_task_started, cleanup_task_tracker
from utils.notifications import send_notification_to_admins
from db_transaction_manager import transaction_scope
from utils.getNextIntraRaterTask import get_next_intra_rater_task



grades_logger = logging.getLogger("grades")


def _parse_selected_features(selected_features_json: str | None) -> list[dict[str, object] | str]:
    """Convert persisted selected feature payload into a python list for display."""
    if not selected_features_json:
        return []

    try:
        parsed = json.loads(selected_features_json)
        if isinstance(parsed, list):
            return parsed
    except JSONDecodeError:
        grades_logger.warning("Failed to parse stored selected_features_json", exc_info=True)

    return []


def register_routes(bp):
    """Register dual grading routes with the blueprint."""
    bp.add_url_rule("/task/<string:task_uuid>/<string:slot_type>", view_func=dual_grading_task, methods=["GET"])
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
            elif slot_type in ['resident2', 'arbitrator']:
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

            # Build serialized feature payload for template hydration
            grading_features = []
            for grading in disease_gradings:
                sorted_features = sorted(
                    grading.features or [],
                    key=lambda feature: ((feature.sr_no or 0), feature.id),
                )
                grading_features.append(
                    {
                        "id": grading.id,
                        "impression": grading.impression,
                        "display_order": grading.display_order,
                        "guidelines": grading.guidelines,
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
            
            # Determine image URL
            image_uuid = None
            if task.encounter_file:
                image_uuid = task.encounter_file.uuid
            elif task.direct_image:
                image_uuid = task.direct_image.uuid

            if image_uuid is None:
                missing_ref = None
                if task.encounter_file_id:
                    missing_ref = f"Encounter file ID {task.encounter_file_id}"
                elif task.direct_image_upload_id:
                    missing_ref = f"Direct upload ID {task.direct_image_upload_id}"

                details = f" ({missing_ref})" if missing_ref else ""
                flash(
                    f"No image is available for this task{details}. The task has been released."
                    " Please contact the system administrator if the issue persists.",
                    "warning",
                )
                send_notification_to_admins(
                    title="Missing Image in Task",
                    message=(
                        f"Task ID {task.id} for user {getattr(current_user, 'id', None)} does not have an"
                        f" associated image{details}."
                    ),
                    notification_type="warning",
                )
                try:
                    cleanup_task_tracker(task.id, current_user.id, slot_type, db)
                except Exception:
                    grades_logger.exception("Failed to cleanup task tracker for missing image task %s", task.id)
                return redirect(url_for("grading.index"))

            # Use the existing grade as the existing_grade parameter
            existing_grade = grade
            existing_selected_features = _parse_selected_features(existing_grade.selected_features_json)

            response = make_response(render_template(
                "grading/dual_grading_task.html",
                task=task,
                disease_gradings=disease_gradings,
                grading_guidelines=grading_guidelines,
                grading_features=grading_features,
                current_slot=slot_type,
                existing_grade=existing_grade,
                existing_selected_features=existing_selected_features,
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
def dual_grading_task(task_uuid: str, slot_type: str):
    """Display a task for dual grading."""
    from flask import session as flask_session

    task_uuid = (task_uuid or "").strip()
    if not task_uuid:
        flash("Invalid task reference.", "danger")
        return redirect(url_for("grading.index"))

    with transaction_scope() as db:
        try:
            # Fetch the task with related data using utility function
            task = fetch_task_with_related_data_by_uuid(db, task_uuid)
            
            if not task:
                flash("Error: Task not found. Please contact the system administrator.", "danger")
                # Send notification to admin about the missing task
                send_notification_to_admins(
                    title="Missing Task Access Attempt",
                    message=f"User {current_user.id} attempted to access non-existent task UUID {task_uuid}. Please investigate and resolve this issue.",
                    notification_type="error"
                )
                return redirect(url_for("grading.index"))

            task_id = task.id

            has_resident_grade = any(grade.role_slot == "resident" for grade in task.grades)
            has_resident2_grade = any(grade.role_slot == "resident2" for grade in task.grades)
            
            # Validate slot_type
            if slot_type not in ['resident', 'resident2', 'arbitrator']:
                flash("Invalid slot type.", "danger")
                return redirect(url_for("grading.index"))
            
            # Check task state validity for the requested slot at assignment time
            state_validity = True
            if slot_type == 'resident':
                # Resident normally sees 'pending' tasks; allow resident2_done when Resident2 grade exists but Resident grade is missing
                allowed_states = ['pending']
                if task.state == 'resident2_done' and has_resident2_grade and not has_resident_grade:
                    allowed_states.append('resident2_done')

                if task.state not in allowed_states:
                    flash(f"Task is no longer available for resident grading (current state: {task.state}).", "danger")
                    state_validity = False
            elif slot_type == 'resident2':
                # Resident2 should only be assigned to 'resident_done' tasks
                if task.state not in ['resident_done']:
                    flash(f"Task is no longer available for resident2 grading (current state: {task.state}).", "danger")
                    state_validity = False
            elif slot_type == 'arbitrator':
                # Arbitrator should only be assigned to 'arbitration' tasks, or 'final' for recent revisions
                if task.state not in ['arbitration', 'final']:
                    flash(f"Task is no longer available for arbitration (current state: {task.state}).", "danger")
                    state_validity = False
            
            if not state_validity:
                return redirect(url_for("grading.index"))

            conflicting_slots = []
            conflict_message = None
            if slot_type == 'resident':
                conflicting_slots = ['resident2']
                conflict_message = "You already graded this task in the resident2 slot."
            elif slot_type == 'resident2':
                conflicting_slots = ['resident']
                conflict_message = "You already graded this task in the resident slot."

            if conflicting_slots and has_user_graded_task(db, current_user.id, task_id, conflicting_slots):
                flash(conflict_message or "You already graded this task in the paired slot.", "warning")
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

            grading_features = []
            for grading in disease_gradings:
                sorted_features = sorted(
                    grading.features or [],
                    key=lambda feature: ((feature.sr_no or 0), feature.id),
                )
                grading_features.append(
                    {
                        "id": grading.id,
                        "impression": grading.impression,
                        "display_order": grading.display_order,
                        "guidelines": grading.guidelines,
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
            
            # Determine image URL
            image_uuid = None
            if task.encounter_file:
                image_uuid = task.encounter_file.uuid
            elif task.direct_image:
                image_uuid = task.direct_image.uuid

            if image_uuid is None:
                missing_ref = None
                if task.encounter_file_id:
                    missing_ref = f"Encounter file ID {task.encounter_file_id}"
                elif task.direct_image_upload_id:
                    missing_ref = f"Direct upload ID {task.direct_image_upload_id}"

                details = f" ({missing_ref})" if missing_ref else ""
                flash(
                    f"No image is available for this task{details}. The task has been released."
                    " Please contact the system administrator if the issue persists.",
                    "warning",
                )
                send_notification_to_admins(
                    title="Missing Image in Task",
                    message=(
                        f"Task ID {task.id} for user {getattr(current_user, 'id', None)} does not have an"
                        f" associated image{details}."
                    ),
                    notification_type="warning",
                )
                try:
                    cleanup_task_tracker(task.id, current_user.id, slot_type, db)
                except Exception:
                    grades_logger.exception("Failed to cleanup task tracker for missing image task %s", task.id)
                return redirect(url_for("grading.index"))

            # Fetch existing grade for this user and slot (for review purposes) using utility function
            existing_grade = fetch_existing_grade_for_user(db, task_id, current_user.id, slot_type)
            existing_selected_features = _parse_selected_features(
                existing_grade.selected_features_json if existing_grade else None
            )
            
            # If this is an arbitration task, fetch resident and resident2 grades to show to the arbitrator
            resident_grade = None
            resident2_grade = None
            if slot_type == 'arbitrator' and task.state == 'arbitration':
                for grade in task.grades:
                    if grade.role_slot == 'resident':
                        resident_grade = grade
                    elif grade.role_slot == 'resident2':
                        resident2_grade = grade
        
            # Check if this is an arbitrator revising their recent grade on a final task
            is_arbitrator_revising_recent = False
            if slot_type == 'arbitrator' and task.state == 'final' and existing_grade:
                arbitrator_eligibility = is_user_eligible_for_revision(db, current_user.id, task_id, slot_type, existing_grade)
                is_arbitrator_revising_recent = arbitrator_eligibility.get("is_recent", False)

            # Check if this is a revision by checking if the user already has a grade for this task and slot
            existing_grade_for_slot = fetch_existing_grade_for_user(db, task_id, current_user.id, slot_type)
            is_revision = existing_grade_for_slot is not None
            
            # Store the start time in the session for fallback
            start_time_key = f"grading_start_time_{task_uuid}_{slot_type}"
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
                resident2_grade=resident2_grade,
                is_arbitrator_revising_recent=is_arbitrator_revising_recent,
                start_time_iso=start_time_iso,  # Pass start time to template as hidden field
                current_user_id=getattr(current_user, "id", None),
                grading_features=grading_features,
                existing_selected_features=existing_selected_features,
            )
        except Exception as e:
            grades_logger.exception("Failed to load grading task: %s", e)
            flash("Failed to load grading task.", "danger")
            return redirect(url_for("grading.index"))

 
@roles_required("resident", "ophthalmologist", "admin")
def dual_grading_submit():
    """Submit a grade for a task."""
    from flask import session as flask_session
    
    task_uuid = (request.form.get("task_uuid") or "").strip()
    slot = (request.form.get("slot") or "").strip().lower()
    label_id = request.form.get("label_id", type=int)
    comment = (request.form.get("comment") or "").strip() or None
    
    # Get selected features from form
    raw_selected_features = request.form.getlist("selected_features")
    selected_feature_ids: list[int] = []
    for raw_feature in raw_selected_features:
        if raw_feature is None or raw_feature == "":
            continue
        try:
            selected_feature_ids.append(int(raw_feature))
        except (TypeError, ValueError):
            flash("Invalid feature selection submitted.", "danger")
            if task_uuid:
                return redirect(url_for("grading.dual_grading_task", task_uuid=task_uuid, slot_type=slot))
            return redirect(url_for("grading.index"))

    # Deduplicate while preserving submission order
    unique_feature_ids: list[int] = []
    seen_feature_ids: set[int] = set()
    for feature_id in selected_feature_ids:
        if feature_id not in seen_feature_ids:
            unique_feature_ids.append(feature_id)
            seen_feature_ids.add(feature_id)

    selected_features_json: str | None = None
    
    # Validate inputs
    if not task_uuid:
        flash("Invalid task reference.", "danger")
        return redirect(url_for("grading.index"))
        
    if not label_id or not isinstance(label_id, int) or label_id <= 0:
        flash("Invalid label ID.", "danger")
        return redirect(url_for("grading.index"))
    
    if slot not in {"resident", "resident2", "arbitrator"}:
        flash("Invalid slot type.", "danger")
        return redirect(url_for("grading.index"))
    
    from db_transaction_manager import transaction_scope
    with transaction_scope() as db:
        try:
            # Use utility function to fetch the task with related data
            task = fetch_task_with_related_data_by_uuid(db, task_uuid)
            if not task:
                flash("Error: Task not found. Please contact the system administrator.", "danger")
                # Send notification to admin about the missing task
                send_notification_to_admins(
                    title="Missing Task Access Attempt",
                    message=f"User {current_user.id} attempted to access non-existent task UUID {task_uuid}. Please investigate and resolve this issue.",
                    notification_type="error"
                )
                return redirect(url_for("grading.index"))
            
            task_id = task.id
            has_resident_grade = any(grade.role_slot == "resident" for grade in task.grades)
            has_resident2_grade = any(grade.role_slot == "resident2" for grade in task.grades)
            
            # Check if this is an arbitrator's revision within 6 hours to allow modifying finalized tasks
            arbitrator_revision_allowed = False
            if slot == "arbitrator":
                # Use utility function to check if arbitrator revision is allowed
                from utils.dualGradingRevisionUtils import is_arbitrator_revision_allowed
                revision_check = is_arbitrator_revision_allowed(db, current_user.id, task_id, slot)
                arbitrator_revision_allowed = revision_check["allowed"]
            
            if task.state == "final" and not arbitrator_revision_allowed:
                flash("This task is already finalized.", "danger")
                return redirect(url_for("grading.dual_grading_task", task_uuid=task_uuid, slot_type=slot))
            
            # Check task state validity at submission time to prevent race conditions 
            # by revalidating the state that was expected when the task was assigned
            state_validity = True
            if slot == 'resident':
                # Resident should only be grading 'pending' or 'resident_done' tasks (for revisions)
                # Allow resident2_done when it was an inconsistency (Resident2 graded first)
                resident_allowed_states = ['pending', 'resident_done']
                if task.state == 'resident2_done' and has_resident2_grade and not has_resident_grade:
                    resident_allowed_states.append('resident2_done')

                if task.state not in resident_allowed_states:
                    flash(f"Task state has changed and is no longer available for resident grading (current state: {task.state}).", "danger")
                    state_validity = False
            elif slot == 'resident2':
                # Resident2 should only be grading 'resident_done', 'resident2_done', or 'arbitration' tasks (for revisions)
                if task.state not in ['resident_done', 'resident2_done', 'arbitration']:
                    flash(f"Task state has changed and is no longer available for resident2 grading (current state: {task.state}).", "danger")
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
                return redirect(url_for("grading.dual_grading_task", task_uuid=task_uuid, slot_type=slot))
            
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
                    return redirect(url_for("grading.dual_grading_task", task_uuid=task_uuid, slot_type=slot))
            
            # Arbitrator exclusion: cannot be prior resident/resident2 grader within 2 weeks
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
                    flash("You cannot arbitrate a task you've graded as resident or resident2 within the last 2 weeks.", "danger")
                    return redirect(url_for("grading.dual_grading_task", task_uuid=task_uuid, slot_type=slot))
            
            # Validate label belongs to task.disease_id using utility function
            disease_gradings = fetch_active_disease_gradings(db, task.disease_id)
            if not disease_gradings:
                flash("Error: No disease gradings available for this task. Please contact the system administrator.", "danger")
                return redirect(url_for("grading.index"))

            label = next((dg for dg in disease_gradings if dg.id == label_id), None)
            if not label:
                flash("Invalid label.", "danger")
                return redirect(url_for("grading.dual_grading_task", task_uuid=task_uuid, slot_type=slot))

            # Validate selected features correspond to the chosen grading
            if unique_feature_ids:
                available_features = (
                    db.query(GradingsFeatures)
                    .filter(GradingsFeatures.disease_grading_id == label_id)
                    .all()
                )
                features_by_id = {feature.id: feature for feature in available_features}
                invalid_features = [fid for fid in unique_feature_ids if fid not in features_by_id]
                if invalid_features:
                    flash("One or more selected features are not valid for the chosen grade.", "danger")
                    return redirect(url_for("grading.dual_grading_task", task_uuid=task_uuid, slot_type=slot))

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

            conflicting_slots = []
            conflict_message = None
            if slot == "resident":
                conflicting_slots = ["resident2"]
                conflict_message = "You already graded this task in the resident2 slot."
            elif slot == "resident2":
                conflicting_slots = ["resident"]
                conflict_message = "You already graded this task in the resident slot."

            if conflicting_slots and has_user_graded_task(db, current_user.id, task_id, conflicting_slots):
                flash(conflict_message or "You already graded this task in the paired slot.", "warning")
                return redirect(url_for("grading.index"))
            
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
            log_message = (
                f"Grade submission [IP: {ip_address}] [user_id: {current_user.id}] "
                f"[Task ID: {task_id}] [Task UUID: {task_uuid}] [Slot Type: {slot}] "
                f"[Disease ID: {task.disease_id}] [Grade: {label_id}] [Type: {grade_type}] [Grade ID: {grade_id}]"
            )
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
            start_time_key = f"grading_start_time_{task_uuid}_{slot}"
            
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
                existing_grade.selected_features_json = selected_features_json
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
                    selected_features_json=selected_features_json,
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
                    grades_logger.info(f"Looking for intra-rater task for user {current_user.id}, disease {disease_id}")
                    intra_task = get_next_intra_rater_task(current_user.id, disease_id)
                    
                    random_value = random.random()
                    grades_logger.info(f"Intra-rater task found: {intra_task is not None}, random value: {random_value} (needs < 0.5)")
                    
                    if intra_task and random_value < 0.5:
                        grades_logger.info(f"Redirecting to intra-rater task {intra_task.uuid} for user {current_user.id}")
                        flash("Grade submitted successfully.", "success")
                        return redirect(
                            url_for(
                                "grading.intra_rater_task",
                                task_uuid=intra_task.uuid,
                                resume_slot=slot,
                                resume_disease_id=disease_id,
                            )
                        )
                    elif intra_task:
                        grades_logger.info(f"Intra-rater task found but random value {random_value} >= 0.5, skipping")
                    else:
                        grades_logger.warning(f"No intra-rater task found for user {current_user.id}, disease {disease_id}")

                    # Try to find the next eligible task with a new transaction scope
                    from db_transaction_manager import transaction_scope

                    next_task = None
                    next_slot_type = slot
                    resident_message = None
                    resident2_message = None

                    # Initialize variables outside transaction scope
                    next_task_uuid = None

                    with transaction_scope() as new_db:
                        if slot in ("resident", "resident2") and current_user.has_role("ophthalmologist"):
                            resident2_candidate = get_next_eligible_resident2_task_atomic(current_user.id, disease_id, db=new_db)
                            if resident2_candidate is not None and not isinstance(resident2_candidate, str):
                                next_task = resident2_candidate
                                next_slot_type = "resident2"
                                # Pre-load UUID while transaction is active
                                next_task_uuid = next_task.uuid
                            else:
                                resident2_message = resident2_candidate

                        if next_task is None and slot in ("resident", "resident2"):
                            resident_candidate = get_next_eligible_resident_task_atomic(current_user.id, disease_id, db=new_db)
                            if resident_candidate is not None and not isinstance(resident_candidate, str):
                                next_task = resident_candidate
                                next_slot_type = "resident"
                                # Pre-load UUID while transaction is active
                                next_task_uuid = next_task.uuid
                            else:
                                resident_message = resident_candidate

                        if next_task is None and slot == "arbitrator":
                            next_task = get_next_eligible_arbitrator_task_atomic(current_user.id, disease_id, db=new_db)
                            if next_task is not None and not isinstance(next_task, str):
                                # Pre-load UUID while transaction is active
                                next_task_uuid = next_task.uuid

                        if next_task is None and slot in ("resident", "resident2"):
                            # Surface resident2 info message first if available
                            if resident2_message not in (None, ""):
                                next_task = resident2_message
                            else:
                                next_task = resident_message

                    # Handle the result outside transaction scope
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
                        # It's a GradingTask object - use pre-loaded UUID
                        flash("Grade submitted successfully.", "success")
                        return redirect(url_for("grading.dual_grading_task", task_uuid=next_task_uuid, slot_type=next_slot_type))
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
