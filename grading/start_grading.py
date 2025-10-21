from flask import redirect, url_for, flash
from flask_login import current_user
from auth.roles import roles_required
from models import Session, Disease
from utils.dualGradingGetNextTasks import get_next_eligible_resident_task_atomic, get_next_eligible_faculty_task_atomic, get_next_eligible_arbitrator_task_atomic
 

def register_routes(bp):
    """Register start grading routes with the blueprint."""
    bp.add_url_rule("/grade/<int:disease_id>/<string:role_slot>", view_func=start_grading, methods=["GET"])


@roles_required("resident", "ophthalmologist")
def start_grading(disease_id: int, role_slot: str):
    """
    Start grading for a specific disease and role slot.
    
    Args:
        disease_id: The ID of the disease to grade
        role_slot: The role slot ('resident', 'faculty', or 'arbitrator')
    """
    # Validate role_slot
    if role_slot not in ['resident', 'faculty', 'arbitrator']:
        flash("Invalid role slot.", "danger")
        return redirect(url_for("grading.index"))
    
    # Check if user has the required role for the slot
    # Allow both residents and ophthalmologists to grade as residents
    if role_slot == 'resident' and not (current_user.has_role('resident') or current_user.has_role('ophthalmologist')):
        flash("You don't have permission to grade as a resident.", "danger")
        return redirect(url_for("grading.index"))
    
    if role_slot in ['faculty', 'arbitrator'] and not current_user.has_role('ophthalmologist'):
        flash("You don't have permission to grade as faculty or arbitrator.", "danger")
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
    
    # Get the next eligible task based on role slot
    task = None
    if role_slot == 'resident':
        task = get_next_eligible_resident_task_atomic(current_user.id, disease_id)
    elif role_slot == 'faculty':
        task = get_next_eligible_faculty_task_atomic(current_user.id, disease_id)
    elif role_slot == 'arbitrator':
        task = get_next_eligible_arbitrator_task_atomic(current_user.id, disease_id)
    
    # Handle the result
    if task is None:
        flash(f"No tasks available for {disease.name} as {role_slot}.", "info")
        return redirect(url_for("grading.index"))
    elif isinstance(task, str):
        # It's a helpful message
        flash(task, "info")
        return redirect(url_for("grading.index"))
    else:
        # It's a GradingTask object
        # Call dual_grading_task directly with slot_type as a parameter
        return redirect(url_for("grading.dual_grading_task", task_id=task.id, slot_type=role_slot))
