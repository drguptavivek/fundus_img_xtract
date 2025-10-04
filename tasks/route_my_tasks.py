"""Route for tasks my-tasks page."""

from __future__ import annotations

from flask import render_template
from auth.roles import roles_required
from utils.upload_eligibility import get_user_lab_unit_ids
from flask_login import current_user

from . import bp


@bp.route("/my-tasks", methods=["GET"])
@roles_required("admin", "data_manager", "ophthalmologist", "optometrist")
def my_tasks() -> str:
    """Page to view user's assigned tasks."""
    user_lab_unit_ids = get_user_lab_unit_ids(current_user.id)
    
    # This would typically query tasks assigned to the current user
    # that belong to their lab units
    return render_template("tasks/my_tasks.html", user_lab_unit_ids=user_lab_unit_ids)