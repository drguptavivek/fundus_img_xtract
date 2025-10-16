from flask import render_template
from flask_login import current_user
from sqlalchemy.orm import joinedload

from auth.roles import roles_required
from db_transaction_manager import get_db_session
from models import GradingTask, LabUnit
from utils.upload_eligibility import get_user_lab_unit_ids
from utils.taskUtils import get_task_detail
from . import bp


@bp.route("/reviewTaskDetails/<int:task_id>", methods=["GET"])
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
        
        # Determine which image object to use for the viewer
        image_object = task.encounter_file if task.encounter_file else task.direct_image

        return render_template(
            "review/task_detail_review.html",
            task=task_details,
            original_task=task,  # For additional properties not in summary
            image_object=image_object
        )