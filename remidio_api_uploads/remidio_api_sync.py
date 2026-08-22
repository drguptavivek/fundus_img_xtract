from __future__ import annotations

from datetime import timedelta

from flask import abort, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from auth.utils import utcnow
from db_transaction_manager import get_db_session
from remidio_api_integration import service as remidio_service

from . import bp


@bp.route("/uploads/remidio-api-sync", methods=["GET"])
@login_required
def remidio_api_sync():
    project_id = _optional_int(request.args.get("project_id"))
    with get_db_session() as db:
        context = remidio_service.list_project_sync_dashboard(db, project_id=project_id, user=current_user)
    if not context["projects"]:
        abort(403)
    if context["selected_project_id"] and context["selected_project_id"] != project_id:
        return redirect(url_for("remidio_api_uploads.remidio_api_sync", project_id=context["selected_project_id"]))
    return render_template("remidio_api_uploads/remidio_api_sync.html", **_with_sync_dates(context))


@bp.route("/uploads/remidio-api-sync/workspace", methods=["GET"])
@login_required
def remidio_api_sync_workspace():
    project_id = _optional_int(request.args.get("project_id"))
    with get_db_session() as db:
        context = remidio_service.list_project_sync_dashboard(db, project_id=project_id, user=current_user)
    if not context["projects"]:
        abort(403)
    return render_template("remidio_api_uploads/_remidio_api_sync_workspace.html", **_with_sync_dates(context))


def _optional_int(value: str | None) -> int | None:
    if value in {None, ""}:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _with_sync_dates(context: dict) -> dict:
    today = utcnow().date()
    context = dict(context)
    context["today"] = today
    context["prospective_start_date"] = today - timedelta(days=1)
    context["prospective_end_date"] = today
    context["historical_start_date"] = today - timedelta(days=7)
    context["historical_end_date"] = today
    return context
