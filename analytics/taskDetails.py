from flask import render_template
from flask_login import current_user
from sqlalchemy.orm import joinedload

from auth.roles import roles_required
from models import GradingTask, LabUnit, Session
from utils.upload_eligibility import get_user_lab_unit_ids
from .taskUtils import get_task_summary
from . import bp


@bp.route("/viewTaskDetails/<int:task_id>", methods=["GET"])
@roles_required("admin", "data_manager", "optometrist")
def view_task_details(task_id: int):
    """View details for a specific task, scoped to user's eligible lab units."""
    db = Session()
    try:
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
        task_details = get_task_summary(task_id)
        
        if not task_details:
            from flask import abort
            abort(404, description="Task not found")
        
        # Determine which image object to use for the viewer
        image_object = task.encounter_file if task.encounter_file else task.direct_image

        return render_template(
            "analytics/task_details.html",
            task=task_details,
            original_task=task,  # For additional properties not in summary
            image_object=image_object
        )
    
    finally:
        db.close()