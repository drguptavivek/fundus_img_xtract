"""Routes for search images."""

from __future__ import annotations

from datetime import datetime, date as _date, time, timezone
from typing import Any, List, Optional

from flask import current_app, render_template, request, url_for, flash, redirect
from flask_login import current_user
from auth.roles import roles_required

from . import bp
from models import (
    Area,
    Camera,
    Disease,
    Hospital,
    LabUnit,
    Session as DBSession,
)
from utils.upload_eligibility import get_user_lab_unit_ids_no_admin_override

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
def search_route() -> str:
    allowed_lab_units = get_user_lab_unit_ids_no_admin_override(current_user.id)
    if not allowed_lab_units:
        flash("No lab unit access.", "warning")
        return redirect(url_for("home.index"))
    return redirect(url_for("search.search_images_route"))
