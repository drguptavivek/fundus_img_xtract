"""Routes for search images."""

from __future__ import annotations

from datetime import datetime, date as _date, time, timezone
from typing import Any, List, Optional

from flask import current_app, render_template, request, url_for
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
from utils.upload_eligibility import get_user_lab_unit_ids

@bp.route("/", methods=["GET"])
@roles_required("admin", "local_admin", "data_manager")
def search_route() -> str:
    return "SEARCH IMAGES ROUTE"
