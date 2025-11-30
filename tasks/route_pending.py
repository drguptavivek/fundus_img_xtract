"""Route for tasks pending page."""

from __future__ import annotations

from flask import render_template
from auth.roles import roles_required
from utils.upload_eligibility import get_user_lab_unit_ids
from flask_login import current_user

from . import bp


@bp.route("/pending", methods=["GET"])
@roles_required("admin", "local_admin", "data_manager", "ophthalmologist", "optometrist")
def pending() -> str:
    """Page to view pending tasks."""
    user_lab_unit_ids = get_user_lab_unit_ids(current_user.id)
    
    # This would typically query pending tasks in user's lab units
    return render_template("tasks/pending.html", user_lab_unit_ids=user_lab_unit_ids)
