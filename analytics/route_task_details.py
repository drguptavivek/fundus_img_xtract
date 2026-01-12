from flask import render_template
from flask_login import current_user
from sqlalchemy.orm import joinedload

from auth.roles import roles_required
from models import GradingTask, LabUnit
from utils.hospital_scoping import apply_scoping
from utils.taskUtils import get_task_summary
from . import bp
from db_transaction_manager import get_db_session


@bp.route("/viewTaskDetails/<int:task_id>", methods=["GET"])
@roles_required("admin", "local_admin", "data_manager", "optometrist")
def view_task_details(task_id: int):
    """View details for a specific task, scoped to user's eligible lab units."""
    with get_db_session() as db:
        # Build query for the task
        query = (
            db.query(GradingTask)
            .filter(GradingTask.id == task_id)
            .options(
                joinedload(GradingTask.disease),
                joinedload(GradingTask.lab_unit),
                joinedload(GradingTask.encounter_file),
                joinedload(GradingTask.direct_image)
            )
        )
        # Apply scoping to ensure task belongs to user's hospital/lab units
        query = apply_scoping(query, GradingTask, current_user, "analytics")
        task = query.first()
        
        if not task:
            from flask import abort
            abort(404, description="Task not found or access denied")
        
        # Use the utility function to get comprehensive task details
        task_details = get_task_summary(db, task_id)
        
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
