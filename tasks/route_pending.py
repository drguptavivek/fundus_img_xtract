"""Route for tasks pending page."""

from __future__ import annotations

from flask import render_template, redirect, url_for, flash
from auth.roles import roles_required
from flask_login import current_user
from db_transaction_manager import get_db_session
from models import LabUnit
from authz.behaviors import clinical_lab_units

from . import bp


@bp.route("/pending", methods=["GET"])
@roles_required(
    "admin",
    "local_admin",
    "fileUploader",
    "ophthalmologist",
    "data_manager",
    "optometrist",
    "project_pi",
    "site_pi",
    "project_admin",
    "collaborator",
)
def pending() -> str:
    """Page to view pending tasks."""
    with get_db_session() as db:
        user_lab_unit_ids = [
            lab_unit.id
            for lab_unit in clinical_lab_units(
                db, db.query(LabUnit), current_user
            ).all()
        ]
    if not user_lab_unit_ids:
        flash("No lab unit access.", "warning")
        return redirect(url_for("home.index"))

    return render_template("tasks/pending.html", user_lab_unit_ids=user_lab_unit_ids)
