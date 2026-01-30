from flask import redirect, url_for, flash
from flask_login import current_user
from auth.roles import roles_required
from models import Session, Disease
from utils.dualGradingGetNextTasks import (
    get_next_eligible_resident_task_atomic,
    get_next_eligible_resident2_task_atomic,
    get_next_eligible_arbitrator_task_atomic,
)
from utils.linkedGradingUtils import get_primary_disease_id
from db_transaction_manager import transaction_scope
  

def register_routes(bp):
    """Register start grading routes with the blueprint."""
    bp.add_url_rule("/grade/<int:disease_id>/<string:role_slot>", view_func=start_grading, methods=["GET"])


@roles_required("resident", "ophthalmologist")
def start_grading(disease_id: int, role_slot: str):
    """
    Start grading for a specific disease and role slot.
    
    Args:
        disease_id: The ID of the disease to grade
        role_slot: The role slot ('resident', 'resident2', or 'arbitrator')
    """
    # Validate role_slot
    if role_slot not in ['resident', 'resident2', 'arbitrator']:
        flash("Invalid role slot.", "danger")
        return redirect(url_for("grading.index"))
    
    # Check if user has the required role for the slot
    # Allow both residents and ophthalmologists to grade as residents
    if role_slot == 'resident' and not (current_user.has_role('resident') or current_user.has_role('ophthalmologist')):
        flash("You don't have permission to grade as a resident.", "danger")
        return redirect(url_for("grading.index"))
    
    if role_slot in ['resident2', 'arbitrator'] and not current_user.has_role('ophthalmologist'):
        flash("You don't have permission to grade as resident2 or arbitrator.", "danger")
        return redirect(url_for("grading.index"))
    
    # Get the disease
    db = Session()
    try:
        disease = db.query(Disease).filter(Disease.id == disease_id).first()
        if not disease:
            flash("Disease not found.", "danger")
            return redirect(url_for("grading.index"))
    finally:
        db.close()
    
    # Get the next eligible task based on role slot using a single transaction scope
    # This prevents DetachedInstanceError by keeping the session open until we access UUID
    with transaction_scope() as db:
        if role_slot in ("resident", "resident2"):
            primary_disease_id = get_primary_disease_id(db, disease_id)
            if primary_disease_id != disease_id:
                flash("Linked disease grading must be completed via the primary disease queue.", "info")
                return redirect(url_for("grading.start_grading", disease_id=primary_disease_id, role_slot=role_slot))

        task = None
        effective_slot = role_slot
        can_grade_resident2 = current_user.has_role('ophthalmologist')

        if role_slot == 'resident':
            resident_message = None
            resident2_message = None

            if can_grade_resident2:
                resident2_candidate = get_next_eligible_resident2_task_atomic(current_user.id, disease_id, db=db)
                if resident2_candidate is not None and not isinstance(resident2_candidate, str):
                    task = resident2_candidate
                    effective_slot = 'resident2'
                else:
                    resident2_message = resident2_candidate

            if task is None:
                resident_candidate = get_next_eligible_resident_task_atomic(current_user.id, disease_id, db=db)
                if resident_candidate is not None and not isinstance(resident_candidate, str):
                    task = resident_candidate
                else:
                    resident_message = resident_candidate

            # Prefer resident2 informational messages if both are messages
            if task is None:
                task = resident2_message if resident2_message not in (None, "") else resident_message

        elif role_slot == 'resident2':
            resident2_candidate = get_next_eligible_resident2_task_atomic(current_user.id, disease_id, db=db)
            if resident2_candidate is not None and not isinstance(resident2_candidate, str):
                task = resident2_candidate
            else:
                resident_candidate = get_next_eligible_resident_task_atomic(current_user.id, disease_id, db=db)
                if resident_candidate is not None and not isinstance(resident_candidate, str):
                    task = resident_candidate
                    effective_slot = 'resident'
                else:
                    if resident2_candidate not in (None, ""):
                        task = resident2_candidate
                    else:
                        task = resident_candidate

        elif role_slot == 'arbitrator':
            task = get_next_eligible_arbitrator_task_atomic(current_user.id, disease_id, db=db)

        # Handle the result within the same transaction
        if task is None:
            flash(f"No tasks available for {disease.name} as {effective_slot}.", "info")
            return redirect(url_for("grading.index"))
        elif isinstance(task, str):
            # It's a helpful message
            flash(task, "info")
            return redirect(url_for("grading.index"))
        else:
            # It's a GradingTask object - access UUID while session is still open
            task_uuid = task.uuid  # Direct access is safe within the transaction
            if not task_uuid:
                flash("Task UUID is missing. Please try again.", "danger")
                return redirect(url_for("grading.index"))

            # Call dual_grading_task directly with slot_type as a parameter
            return redirect(url_for("grading.dual_grading_task", task_uuid=task_uuid, slot_type=effective_slot))
