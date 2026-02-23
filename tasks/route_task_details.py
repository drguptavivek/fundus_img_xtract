from flask import render_template
from flask_login import current_user
from sqlalchemy import or_
from sqlalchemy.orm import joinedload

from auth.roles import roles_required
from db_transaction_manager import get_db_session
from models import GradingTask, LabUnit

from utils.hospital_scoping import apply_scoping
from utils.taskUtils import get_task_detail
from . import bp


@bp.route("/viewTaskDetails/<int:task_id>", methods=["GET"])
@roles_required(
    "admin",
    "local_admin",
    "fileUploader",
    "ophthalmologist",
    "data_manager",
    "resident",
    "optometrist",
)
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
        query = apply_scoping(query, GradingTask, current_user, "view")
        task = query.first()
        
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

        # Render template within the same session to avoid detached instance errors
        return render_template(
            "tasks/task_details.html",
            task=task_details,
            original_task=task,  # For additional properties not in summary
            image_object=image_object
        )


@bp.route("/all-tasks/viewer/<string:image_uuid>", methods=["GET"])
@roles_required(
    "admin",
    "local_admin",
    "fileUploader",
    "ophthalmologist",
    "data_manager",
    "resident",
    "optometrist",
)
def all_tasks_viewer(image_uuid: str):
    """Serve the grading viewer card for the all-tasks list."""
    with get_db_session() as db:
        query = (
            db.query(GradingTask)
            .filter(
                or_(
                    GradingTask.encounter_file.has(uuid=image_uuid),
                    GradingTask.direct_image.has(uuid=image_uuid),
                ),
            )
            .options(joinedload(GradingTask.encounter_file), joinedload(GradingTask.direct_image))
        )
        query = apply_scoping(query, GradingTask, current_user, "view")
        task = query.first()
        if not task:
            from flask import abort
            abort(404, description="Task not found or access denied")

        image_object = task.encounter_file if task.encounter_file else task.direct_image
        return render_template(
            "partials/_grading_card.html",
            image=image_object,
            image_uuid=image_uuid,
            show_annotation_sidebar=False,
            show_presets=False,
            show_save_preset=False,
            show_cdr_controls=False,
            lite_viewer_mode=True,
        )
