"""Route for tasks index page."""

from __future__ import annotations

from flask import render_template
from auth.roles import roles_required
from utils.upload_eligibility import get_user_lab_unit_ids
from flask_login import current_user

from . import bp


@bp.route("/", methods=["GET"])
@roles_required("admin", "local_admin", "data_manager", "ophthalmologist", "optometrist")
def index() -> str:
    """Main tasks page."""
    user_lab_unit_ids = get_user_lab_unit_ids(current_user.id)
    
    # You can expand this with actual task data as needed
    return render_template("tasks/index.html", user_lab_unit_ids=user_lab_unit_ids)
