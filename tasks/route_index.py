"""Route for tasks index page."""

from __future__ import annotations

from flask import render_template, redirect, url_for, flash
from auth.roles import roles_required
from utils.upload_eligibility import get_user_lab_unit_ids_no_admin_override
from flask_login import current_user

from . import bp


@bp.route("/", methods=["GET"])
@roles_required(
    "admin",
    "local_admin",
    "fileUploader",
    "ophthalmologist",
    "data_manager",
    "resident",
    "optometrist",
)
def index() -> str:
    """Main tasks page."""
    user_lab_unit_ids = get_user_lab_unit_ids_no_admin_override(current_user.id)
    if not user_lab_unit_ids:
        flash("No lab unit access.", "warning")
        return redirect(url_for("home.index"))

    return render_template("tasks/index.html", user_lab_unit_ids=user_lab_unit_ids)
