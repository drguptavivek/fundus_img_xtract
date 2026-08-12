"""Thin HTML routes for the non-PII project review workspace."""
from __future__ import annotations

from flask import abort, render_template, request
from flask_login import current_user, login_required

from db_transaction_manager import transaction_scope

from .exceptions import ProjectReviewNotFound
from .service import get_gradings, get_summary, get_uploads, list_projects
from . import bp


@bp.route("/")
@login_required
def index():
    with transaction_scope() as db:
        projects = list_projects(db, user=current_user)
    if projects:
        return render_template("projects/index.html", projects=projects)
    return render_template("projects/empty.html")


@bp.route("/<int:project_id>/summary")
@login_required
def summary(project_id: int):
    try:
        with transaction_scope() as db:
            data = get_summary(db, user=current_user, project_id=project_id)
            projects = list_projects(db, user=current_user)
    except ProjectReviewNotFound:
        abort(404)
    return render_template("projects/summary.html", data=data, projects=projects)


@bp.route("/<int:project_id>/uploads")
@login_required
def uploads(project_id: int):
    try:
        with transaction_scope() as db:
            data = get_uploads(
                db,
                user=current_user,
                project_id=project_id,
                page=request.args.get("page", 1, type=int),
            )
            projects = list_projects(db, user=current_user)
    except ProjectReviewNotFound:
        abort(404)
    return render_template("projects/uploads.html", data=data, projects=projects)


@bp.route("/<int:project_id>/gradings")
@login_required
def gradings(project_id: int):
    try:
        with transaction_scope() as db:
            data = get_gradings(db, user=current_user, project_id=project_id)
            projects = list_projects(db, user=current_user)
    except ProjectReviewNotFound:
        abort(404)
    return render_template("projects/gradings.html", data=data, projects=projects)
