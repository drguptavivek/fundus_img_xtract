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
from utils.log_sanitize import sanitize_log_value

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
from utils.linkedGradingUtils import get_linked_disease_ids, get_primary_disease_id
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
            task = fetch_task_with_related_data_by_uuid(db, task_uuid, user=current_user)
            
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
            
            def _build_grading_data(task_obj: GradingTask):
                disease_gradings = fetch_active_disease_gradings(db, task_obj.disease_id)
                if not disease_gradings:
                    flash(
                        "Error: No disease gradings available for this task. Please contact the system administrator.",
                        "danger",
                    )
                    send_notification_to_admins(
                        title="Missing Disease Gradings in Task",
                        message=(
                            f"Task ID {task_obj.id} does not have associated disease gradings."
                            " Please investigate and resolve this issue."
                        ),
                        notification_type="error",
                    )
                    return None

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

                return {
                    "disease_gradings": disease_gradings,
                    "grading_guidelines": grading_guidelines,
                    "grading_features": grading_features,
                }

            grading_data = _build_grading_data(task)
            if grading_data is None:
                return redirect(url_for("grading.index"))

            disease_gradings = grading_data["disease_gradings"]
            grading_guidelines = grading_data["grading_guidelines"]
            grading_features = grading_data["grading_features"]
            
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
            existing_grade = fetch_existing_grade_for_user(db, task_id, current_user.id, slot_type, user=current_user)
            existing_selected_features = _parse_selected_features(
                existing_grade.selected_features_json if existing_grade else None
            )

            linked_mode = False
            linked_panels = []
            linked_grading_data = {}
            show_save_next = existing_grade is None
            primary_task_uuid = task.uuid

            if slot_type in ("resident", "resident2", "arbitrator"):
                primary_disease_id = get_primary_disease_id(db, task.disease_id)
                if primary_disease_id != task.disease_id:
                    # Redirect linked disease grading to the primary task for this image
                    primary_task = None
                    if task.encounter_file_id:
                        primary_task = db.query(GradingTask).filter(
                            GradingTask.encounter_file_id == task.encounter_file_id,
                            GradingTask.disease_id == primary_disease_id,
                        ).first()
                    elif task.direct_image_upload_id:
                        primary_task = db.query(GradingTask).filter(
                            GradingTask.direct_image_upload_id == task.direct_image_upload_id,
                            GradingTask.disease_id == primary_disease_id,
                        ).first()
                    if primary_task:
                        return redirect(
                            url_for(
                                "grading.dual_grading_task",
                                task_uuid=primary_task.uuid,
                                slot_type=slot_type,
                            )
                        )

                linked_disease_ids = get_linked_disease_ids(db, task.disease_id)
                if linked_disease_ids:
                    linked_task_list = [task]
                    for linked_disease_id in linked_disease_ids:
                        linked_task = None
                        if task.encounter_file_id:
                            linked_task = db.query(GradingTask).filter(
                                GradingTask.encounter_file_id == task.encounter_file_id,
                                GradingTask.disease_id == linked_disease_id,
                            ).first()
                        elif task.direct_image_upload_id:
                            linked_task = db.query(GradingTask).filter(
                                GradingTask.direct_image_upload_id == task.direct_image_upload_id,
                                GradingTask.disease_id == linked_disease_id,
                            ).first()

                        if linked_task is None and image_uuid:
                            try:
                                linked_task = svc_ensure_task(image_uuid, linked_disease_id, db)
                            except Exception as ensure_error:
                                grades_logger.exception(
                                    "Failed to ensure linked task for disease %s: %s",
                                    linked_disease_id,
                                    ensure_error,
                                )
                                flash(
                                    f"Failed to initialize linked grading task for disease ID {linked_disease_id}. Please contact support.",
                                    "danger",
                                )
                                return redirect(url_for("grading.index"))

                        if linked_task is not None:
                            linked_task_list.append(linked_task)

                    for panel_task in linked_task_list:
                        panel_task_id = panel_task.id
                        panel_conflicting_slots = []
                        panel_conflict_message = None
                        if slot_type == 'resident':
                            panel_conflicting_slots = ['resident2']
                            panel_conflict_message = "You already graded this task in the resident2 slot."
                        elif slot_type == 'resident2':
                            panel_conflicting_slots = ['resident']
                            panel_conflict_message = "You already graded this task in the resident slot."

                        if panel_conflicting_slots and has_user_graded_task(
                            db, current_user.id, panel_task_id, panel_conflicting_slots
                        ):
                            flash(panel_conflict_message or "You already graded this task in the paired slot.", "warning")
                            return redirect(url_for("grading.index"))

                        is_eligible = get_user_eligibility_for_task(db, current_user.id, panel_task_id, slot_type)
                        eligibility_error = None

                        if not is_eligible:
                            eligibility_error = "You are not eligible to grade this linked task."
                            # Continue to load panel but mark it

                        if slot_type == 'resident':
                            allowed_states = ['pending']
                            panel_has_resident_grade = any(
                                grade.role_slot == "resident" for grade in panel_task.grades
                            )
                            panel_has_resident2_grade = any(
                                grade.role_slot == "resident2" for grade in panel_task.grades
                            )
                            if panel_task.state == 'resident2_done' and panel_has_resident2_grade and not panel_has_resident_grade:
                                allowed_states.append('resident2_done')
                            # Final tasks shown read-only for medical context, not skipped
                            if panel_task.state not in allowed_states and panel_task.state != 'final':
                                flash(
                                    f"Task {panel_task.id} is no longer available for resident grading (state: {panel_task.state}).",
                                    "danger",
                                )
                                return redirect(url_for("grading.index"))
                        elif slot_type == 'resident2':
                            # Final tasks shown read-only for medical context, not skipped
                            if panel_task.state not in ['resident_done', 'final']:
                                flash(
                                    f"Task {panel_task.id} is no longer available for resident2 grading (state: {panel_task.state}).",
                                    "danger",
                                )
                                return redirect(url_for("grading.index"))
                        elif slot_type == 'arbitrator':
                            # Arbitrator can see and grade 'arbitration' state tasks
                            # Can also revise 'final' tasks if eligible for revision
                            # Other states are shown read-only for context
                            if panel_task.state not in ['arbitration', 'final']:
                                # Task not ready for arbitration, will show read-only
                                # This allows arbitrator to see related diseases' grades for context
                                pass

                        panel_grading_data = _build_grading_data(panel_task)
                        if panel_grading_data is None:
                            return redirect(url_for("grading.index"))

                        panel_existing_grade = fetch_existing_grade_for_user(
                            db, panel_task_id, current_user.id, slot_type, user=current_user
                        )
                        panel_existing_features = _parse_selected_features(
                            panel_existing_grade.selected_features_json if panel_existing_grade else None
                        )

                        if panel_existing_grade is not None:
                            show_save_next = False

                        # Determine read_only status for this panel
                        panel_read_only = eligibility_error is not None
                        if slot_type == 'arbitrator':
                            # Arbitrator can grade 'arbitration' tasks
                            # For 'final' tasks, check if eligible for revision
                            if panel_task.state == 'final':
                                # Check if arbitrator is revising this specific panel task
                                panel_arbitrator_revision = is_arbitrator_revision_allowed(
                                    db, current_user.id, panel_task_id, slot_type
                                )
                                panel_read_only = not panel_arbitrator_revision.get('allowed', False)
                            elif panel_task.state != 'arbitration':
                                # Not ready for arbitration, show read-only for context
                                panel_read_only = True
                        else:
                            # For resident/resident2, only final is read-only
                            panel_read_only = panel_read_only or (panel_task.state == "final")

                        linked_panels.append(
                            {
                                "task": panel_task,
                                "disease_gradings": panel_grading_data["disease_gradings"],
                                "grading_guidelines": panel_grading_data["grading_guidelines"],
                                "grading_features": panel_grading_data["grading_features"],
                                "existing_grade": panel_existing_grade,
                                "existing_selected_features": panel_existing_features,
                                "read_only": panel_read_only,
                                "eligibility_error": eligibility_error,
                            }
                        )

                        linked_grading_data[panel_task.uuid] = {
                            "guidelines": panel_grading_data["grading_guidelines"],
                            "features": panel_grading_data["grading_features"],
                            "existingSelectedFeatures": panel_existing_features,
                            "readOnly": panel_task.state == "final",
                            "taskUuid": panel_task.uuid,
                        }

                    linked_mode = len(linked_panels) > 1
            
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
            existing_grade_for_slot = fetch_existing_grade_for_user(db, task_id, current_user.id, slot_type, user=current_user)
            is_revision = existing_grade_for_slot is not None
            
            # Store the start time in the session for fallback
            start_time_key = f"grading_start_time_{task_uuid}_{slot_type}"
            start_time_iso = datetime.now(timezone.utc).isoformat()
            flask_session[start_time_key] = start_time_iso
            
            # Mark that the user has started working on this task for stuck task tracking
            # but only if this is not a revision (i.e., user doesn't already have a grade for this slot)
            if linked_mode and slot_type in ("resident", "resident2"):
                for panel in linked_panels:
                    if not panel.get("existing_grade"):
                        mark_task_started(panel["task"].id, current_user.id, slot_type)
            elif not is_revision:
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
                existing_grade_in_header=not linked_mode,
                resident_grade=resident_grade,
                resident2_grade=resident2_grade,
                is_arbitrator_revising_recent=is_arbitrator_revising_recent,
                start_time_iso=start_time_iso,  # Pass start time to template as hidden field
                current_user_id=getattr(current_user, "id", None),
                grading_features=grading_features,
                existing_selected_features=existing_selected_features,
                linked_mode=linked_mode,
                linked_panels=linked_panels,
                linked_grading_data=linked_grading_data,
                show_save_next=show_save_next,
                primary_task_uuid=primary_task_uuid,
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
    linked_task_uuids_raw = (request.form.get("linked_task_uuids") or "").strip()
    primary_task_uuid = (request.form.get("primary_task_uuid") or "").strip()
    slot = (request.form.get("slot") or "").strip().lower()
    label_id = request.form.get("label_id", type=int)
    comment = (request.form.get("comment") or "").strip() or None
    is_linked_submission = bool(linked_task_uuids_raw)
    
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
    if not task_uuid and not linked_task_uuids_raw:
        flash("Invalid task reference.", "danger")
        return redirect(url_for("grading.index"))
        
    if not is_linked_submission and (not label_id or not isinstance(label_id, int) or label_id <= 0):
        flash("Invalid label ID.", "danger")
        return redirect(url_for("grading.index"))
    
    if slot not in {"resident", "resident2", "arbitrator"}:
        flash("Invalid slot type.", "danger")
        return redirect(url_for("grading.index"))
    
    from db_transaction_manager import transaction_scope
    with transaction_scope() as db:
        try:
            task_uuids = []
            if is_linked_submission:
                task_uuids = [u.strip() for u in linked_task_uuids_raw.split(",") if u.strip()]
            elif task_uuid:
                task_uuids = [task_uuid]

            if not task_uuids:
                flash("Invalid task reference.", "danger")
                return redirect(url_for("grading.index"))

            redirect_task_uuid = primary_task_uuid or task_uuid or task_uuids[0]
            primary_task = None

            for current_task_uuid in task_uuids:
                label_key = f"label_id_{current_task_uuid}" if is_linked_submission else "label_id"
                comment_key = f"comment_{current_task_uuid}" if is_linked_submission else "comment"
                features_key = f"selected_features_{current_task_uuid}" if is_linked_submission else "selected_features"
                start_time_key_form = f"start_time_iso_{current_task_uuid}" if is_linked_submission else "start_time_iso"

                current_label_id = request.form.get(label_key, type=int)
                current_comment = (request.form.get(comment_key) or "").strip() or None

                if not current_label_id or not isinstance(current_label_id, int) or current_label_id <= 0:
                    flash("Invalid label ID.", "danger")
                    return redirect(url_for("grading.dual_grading_task", task_uuid=redirect_task_uuid, slot_type=slot))

                raw_selected_features = request.form.getlist(features_key)
                selected_feature_ids = []
                for raw_feature in raw_selected_features:
                    if raw_feature is None or raw_feature == "":
                        continue
                    try:
                        selected_feature_ids.append(int(raw_feature))
                    except (TypeError, ValueError):
                        flash("Invalid feature selection submitted.", "danger")
                        return redirect(url_for("grading.dual_grading_task", task_uuid=redirect_task_uuid, slot_type=slot))

                unique_feature_ids = []
                seen_feature_ids = set()
                for feature_id in selected_feature_ids:
                    if feature_id not in seen_feature_ids:
                        unique_feature_ids.append(feature_id)
                        seen_feature_ids.add(feature_id)

                selected_features_json = None

                task = fetch_task_with_related_data_by_uuid(db, current_task_uuid, user=current_user)
                if not task:
                    flash("Error: Task not found. Please contact the system administrator.", "danger")
                    send_notification_to_admins(
                        title="Missing Task Access Attempt",
                        message=(
                            f"User {current_user.id} attempted to access non-existent task UUID"
                            f" {current_task_uuid}. Please investigate and resolve this issue."
                        ),
                        notification_type="error",
                    )
                    return redirect(url_for("grading.index"))

                if primary_task is None:
                    primary_task = task

                task_id = task.id
                has_resident_grade = any(grade.role_slot == "resident" for grade in task.grades)
                has_resident2_grade = any(grade.role_slot == "resident2" for grade in task.grades)

                arbitrator_revision_allowed = False
                if slot == "arbitrator":
                    from utils.dualGradingRevisionUtils import is_arbitrator_revision_allowed
                    revision_check = is_arbitrator_revision_allowed(db, current_user.id, task_id, slot)
                    arbitrator_revision_allowed = revision_check["allowed"]

                if task.state == "final" and not arbitrator_revision_allowed:
                    flash("This task is already finalized.", "danger")
                    return redirect(url_for("grading.dual_grading_task", task_uuid=redirect_task_uuid, slot_type=slot))

                state_validity = True
                if slot == 'resident':
                    resident_allowed_states = ['pending', 'resident_done']
                    if task.state == 'resident2_done' and has_resident2_grade and not has_resident_grade:
                        resident_allowed_states.append('resident2_done')
                    if task.state not in resident_allowed_states:
                        flash(
                            f"Task state has changed and is no longer available for resident grading (current state: {task.state}).",
                            "danger",
                        )
                        state_validity = False
                elif slot == 'resident2':
                    if task.state not in ['resident_done', 'resident2_done', 'arbitration']:
                        flash(
                            f"Task state has changed and is no longer available for resident2 grading (current state: {task.state}).",
                            "danger",
                        )
                        state_validity = False
                elif slot == 'arbitrator':
                    if task.state not in ['arbitration', 'final']:
                        flash(
                            f"Task state has changed and is no longer available for arbitration (current state: {task.state}).",
                            "danger",
                        )
                        state_validity = False

                if not state_validity:
                    return redirect(url_for("grading.index"))

                if not get_user_eligibility_for_task(db, current_user.id, task_id, slot):
                    if is_linked_submission:
                        grades_logger.warning(
                            "Skipping ineligible linked task %s for user %s",
                            task_id,
                            sanitize_log_value(current_user.id),
                        )
                        continue
                    flash("You are not eligible to grade this task for the selected role.", "danger")
                    return redirect(url_for("grading.dual_grading_task", task_uuid=redirect_task_uuid, slot_type=slot))

                if slot == "arbitrator":
                    if not current_user.has_role('ophthalmologist'):
                        flash("You don't have permission to grade as arbitrator.", "danger")
                        return redirect(url_for("grading.index"))

                    eligibility = check_arbitration_eligibility(db, current_user.id, task.disease_id, task.lab_unit_id)
                    if not eligibility:
                        flash("You are not eligible to arbitrate for this task.", "danger")
                        return redirect(url_for("grading.dual_grading_task", task_uuid=redirect_task_uuid, slot_type=slot))

                if slot == "arbitrator":
                    existing_grade = fetch_existing_grade_for_user(db, task_id, current_user.id, slot, user=current_user)
                    is_arbitrator_revision = (
                        existing_grade and
                        existing_grade.role_slot == "arbitrator" and
                        existing_grade.grader_user_id == current_user.id
                    )

                    if not is_arbitrator_revision and _has_user_graded_task_2weeks(db, current_user.id, task_id):
                        flash(
                            "You cannot arbitrate a task you've graded as resident or resident2 within the last 2 weeks.",
                            "danger",
                        )
                        return redirect(url_for("grading.dual_grading_task", task_uuid=redirect_task_uuid, slot_type=slot))

                disease_gradings = fetch_active_disease_gradings(db, task.disease_id)
                if not disease_gradings:
                    flash("Error: No disease gradings available for this task. Please contact the system administrator.", "danger")
                    return redirect(url_for("grading.index"))

                label = next((dg for dg in disease_gradings if dg.id == current_label_id), None)
                if not label:
                    flash("Invalid label.", "danger")
                    return redirect(url_for("grading.dual_grading_task", task_uuid=redirect_task_uuid, slot_type=slot))

                if unique_feature_ids:
                    available_features = (
                        db.query(GradingsFeatures)
                        .filter(GradingsFeatures.disease_grading_id == current_label_id)
                        .all()
                    )
                    features_by_id = {feature.id: feature for feature in available_features}
                    invalid_features = [fid for fid in unique_feature_ids if fid not in features_by_id]
                    if invalid_features:
                        flash("One or more selected features are not valid for the chosen grade.", "danger")
                        return redirect(url_for("grading.dual_grading_task", task_uuid=redirect_task_uuid, slot_type=slot))

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

                existing_grade = fetch_existing_grade_for_user(db, task_id, current_user.id, slot, user=current_user)
                had_existing_grade = existing_grade is not None

                prev_grade_id = None
                prev_comment = None
                if had_existing_grade:
                    prev_grade_id = existing_grade.disease_grading_id
                    prev_comment = existing_grade.comment

                timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                ip_address = request.environ.get('HTTP_X_REAL_IP', request.remote_addr)
                grade_type = "revision" if had_existing_grade else "new"
                grade_id = existing_grade.id if had_existing_grade and existing_grade else "N/A"
                log_message = (
                    f"Grade submission [IP: {ip_address}] [user_id: {current_user.id}] "
                    f"[Task ID: {task_id}] [Task UUID: {current_task_uuid}] [Slot Type: {slot}] "
                    f"[Disease ID: {task.disease_id}] [Grade: {current_label_id}] [Type: {grade_type}] [Grade ID: {grade_id}]"
                )
                if current_comment:
                    log_message += f" [Comments - {current_comment}]"
                if had_existing_grade and prev_grade_id is not None:
                    prev_comment_display = prev_comment if prev_comment else "None"
                    log_message += f" [Previous Grade: {prev_grade_id}] [Previous Comment: {prev_comment_display}]"
                grades_logger.info(log_message)

                time_taken = None
                session_key = f"grading_start_time_{current_task_uuid}_{slot}"
                start_time_str = request.form.get(start_time_key_form)
                if not start_time_str:
                    start_time_str = flask_session.get(session_key)
                if start_time_str:
                    try:
                        start_time = datetime.fromisoformat(start_time_str)
                        if start_time.tzinfo is None:
                            start_time = start_time.replace(tzinfo=timezone.utc)
                        current_time = datetime.now(timezone.utc)
                        time_taken = int((current_time - start_time).total_seconds())
                        flask_session.pop(session_key, None)
                    except (ValueError, TypeError):
                        pass

                disease_grading = db.query(DiseaseGrading).filter(DiseaseGrading.id == current_label_id).first()
                disease = None
                if disease_grading:
                    disease = db.query(Disease).filter(Disease.id == disease_grading.disease_id).first()

                if existing_grade:
                    existing_grade.disease_grading_id = current_label_id
                    existing_grade.comment = current_comment
                    existing_grade.selected_features_json = selected_features_json
                    existing_grade.time_taken = time_taken
                    existing_grade.disease_name = disease.name if disease else None
                    existing_grade.grade_name = disease_grading.impression if disease_grading else None
                    existing_grade.grade_description = disease_grading.guidelines if disease_grading else None
                    db.add(existing_grade)
                    db.flush()
                else:
                    new_grade = Grade(
                        task_id=task.id,
                        grader_user_id=current_user.id,
                        role_slot=slot,
                        disease_grading_id=current_label_id,
                        comment=current_comment,
                        selected_features_json=selected_features_json,
                        time_taken=time_taken,
                        disease_name=disease.name if disease else None,
                        grade_name=disease_grading.impression if disease_grading else None,
                        grade_description=disease_grading.guidelines if disease_grading else None,
                    )
                    db.add(new_grade)
                    db.flush()
                    existing_grade = new_grade

                from utils.dualGradingConsensusUtils import update_task_state_based_on_grades
                update_task_state_based_on_grades(task.id, db)

                from utils.dualGradingConsensusUtils import create_or_update_consensus
                create_or_update_consensus(task.id, db)

                if not had_existing_grade:
                    from utils.dualGradingStuckTaskCleanup import cleanup_task_tracker
                    cleanup_task_tracker(task_id, current_user.id, slot, db)

            disease_id = primary_task.disease_id if primary_task else None
            if disease_id is None and task_uuids:
                fallback_task = fetch_task_with_related_data_by_uuid(db, task_uuids[0], user=current_user)
                disease_id = fallback_task.disease_id if fallback_task else None
            
            # Check if we should go to the next task
            action = (request.form.get("action") or "").strip().lower()
            if action == "save_next":
                # Since we're closing the current session to get the next task,
                # we need to commit our changes first
                db.commit()
                try:
                    grades_logger.info(
                        "Looking for intra-rater task for user %s, disease %s",
                        sanitize_log_value(current_user.id),
                        sanitize_log_value(disease_id),
                    )
                    intra_task = get_next_intra_rater_task(current_user.id, disease_id)
                    
                    random_value = random.random()
                    grades_logger.info(
                        "Intra-rater task found: %s, random value: %s (needs < 0.5)",
                        sanitize_log_value(intra_task is not None),
                        sanitize_log_value(random_value),
                    )
                    
                    if intra_task and random_value < 0.5:
                        grades_logger.info(
                            "Redirecting to intra-rater task %s for user %s",
                            sanitize_log_value(intra_task.uuid),
                            sanitize_log_value(current_user.id),
                        )
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
                        grades_logger.info(
                            "Intra-rater task found but random value %s >= 0.5, skipping",
                            sanitize_log_value(random_value),
                        )
                    else:
                        grades_logger.warning(
                            "No intra-rater task found for user %s, disease %s",
                            sanitize_log_value(current_user.id),
                            sanitize_log_value(disease_id),
                        )

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
                        # Prefer resident queue messaging if both queues are empty
                        if resident_message not in (None, ""):
                            next_task = resident_message
                        else:
                            next_task = resident2_message

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
