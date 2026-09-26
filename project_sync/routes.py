"""Page routes for project data sync (initial pages and HTMX fragments only).

All mutations go through ``api/project_sync.py``.
"""
from __future__ import annotations

from flask import Blueprint, render_template, request
from flask_login import current_user, login_required

from auth.roles import roles_required
from db_transaction_manager import transaction_scope

from .service import eligible_projects, list_admin_grants, list_user_grants, sync_enabled

bp = Blueprint("project_sync_pages", __name__, url_prefix="/project-sync")


def _user_workspace_context(db) -> dict:
    enabled = sync_enabled()
    return {
        "sync_enabled": enabled,
        "projects": eligible_projects(db, current_user) if enabled else [],
        "grants": list_user_grants(db, user=current_user),
    }


@bp.route("/", methods=["GET"])
@login_required
def index():
    with transaction_scope() as db:
        return render_template("project_sync/index.html", **_user_workspace_context(db))


@bp.route("/workspace", methods=["GET"])
@login_required
def workspace():
    with transaction_scope() as db:
        return render_template("project_sync/_workspace.html", **_user_workspace_context(db))


@bp.route("/confirm", methods=["GET"])
@login_required
def confirm():
    return render_template("project_sync/confirm.html", token=request.args.get("token", ""))


@bp.route("/admin", methods=["GET"])
@roles_required("admin")
def admin():
    with transaction_scope() as db:
        return render_template(
            "project_sync/admin.html",
            sync_enabled=sync_enabled(),
            grants=list_admin_grants(db, admin=current_user),
        )


@bp.route("/admin/workspace", methods=["GET"])
@roles_required("admin")
def admin_workspace():
    with transaction_scope() as db:
        return render_template(
            "project_sync/_admin_workspace.html",
            sync_enabled=sync_enabled(),
            grants=list_admin_grants(db, admin=current_user),
        )
