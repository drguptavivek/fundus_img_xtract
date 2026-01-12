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
from utils.hospital_scoping import apply_scoping

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
    with DBSession() as db:
        # Get allowed lab units via scoping
        lu_query = db.query(LabUnit)
        lu_query = apply_scoping(lu_query, LabUnit, current_user, "view")
        allowed_lab_units = [lu.id for lu in lu_query.all()]
    if not allowed_lab_units:
        flash("No lab unit access.", "warning")
        return redirect(url_for("home.index"))
    return redirect(url_for("search.search_images_route"))
