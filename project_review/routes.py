"""Thin HTML routes for the non-PII project review workspace."""
from __future__ import annotations

from flask import abort, render_template, request, url_for
from flask_login import current_user, login_required

from db_transaction_manager import transaction_scope
from data_authorization.policy import project_capabilities

from .exceptions import ProjectReviewNotFound
from .service import get_gradings, get_summary, get_uploads, list_projects
from . import bp


@bp.route("/")
@login_required
def index():
    with transaction_scope() as db:
        projects = list_projects(db, user=current_user)
        capabilities_by_project = {
            project.id: project_capabilities(db, user=current_user, project_id=project.id)
            for project in projects
        }
    if projects:
        destinations = {
            project.id: _project_landing_url(
                project.id,
                capabilities_by_project[project.id],
            )
            for project in projects
        }
        return render_template(
            "projects/index.html",
            projects=projects,
            destinations=destinations,
        )
    return render_template("projects/empty.html")


@bp.route("/<int:project_id>/summary")
@login_required
def summary(project_id: int):
    try:
        with transaction_scope() as db:
            capabilities = project_capabilities(db, user=current_user, project_id=project_id)
            if not capabilities.can_view_overview:
                abort(403)
            data = get_summary(db, user=current_user, project_id=project_id)
            projects = list_projects(db, user=current_user)
    except ProjectReviewNotFound:
        abort(404)
    return render_template("projects/summary.html", data=data, projects=projects, capabilities=capabilities)


@bp.route("/<int:project_id>/uploads")
@login_required
def uploads(project_id: int):
    try:
        with transaction_scope() as db:
            capabilities = project_capabilities(db, user=current_user, project_id=project_id)
            if not capabilities.can_view_overview:
                abort(403)
            data = get_uploads(
                db,
                user=current_user,
                project_id=project_id,
                page=request.args.get("page", 1, type=int),
            )
            projects = list_projects(db, user=current_user)
    except ProjectReviewNotFound:
        abort(404)
    return render_template("projects/uploads.html", data=data, projects=projects, capabilities=capabilities)


@bp.route("/<int:project_id>/gradings")
@login_required
def gradings(project_id: int):
    try:
        with transaction_scope() as db:
            capabilities = project_capabilities(db, user=current_user, project_id=project_id)
            if not capabilities.can_view_overview:
                abort(403)
            data = get_gradings(db, user=current_user, project_id=project_id)
            projects = list_projects(db, user=current_user)
    except ProjectReviewNotFound:
        abort(404)
    return render_template("projects/gradings.html", data=data, projects=projects, capabilities=capabilities)


def _project_landing_url(project_id: int, capabilities) -> str:
    if capabilities.can_view_overview:
        return url_for("projects.summary", project_id=project_id)
    upload_routes = (
        ("direct_image", "direct_uploads.upload", {}),
        ("pregraded", "direct_uploads.pregraded_upload", {}),
        ("remidio", "remedio_zip_uploads.upload_form", {"ingest_mode": "legacy_remidio"}),
        ("encounter_set", "remedio_zip_uploads.upload_form", {"ingest_mode": "encounter_set"}),
    )
    for upload_kind, endpoint, values in upload_routes:
        if upload_kind in capabilities.upload_kinds:
            return url_for(endpoint, project_id=project_id, **values)
    if capabilities.can_sync_remidio:
        return url_for("remidio_api_uploads.remidio_api_sync", project_id=project_id)
    return url_for("projects.summary", project_id=project_id)
