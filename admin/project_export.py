"""Admin page for downloading DuckDB export packages (project or no-project).

The page is a shell; HTMX loads the form fragment, and the download itself is the
documented API (``api/project_export_package.py``).
"""
from __future__ import annotations

from flask import render_template

from auth.roles import roles_required
from db_transaction_manager import transaction_scope
from project_export import export_options


@roles_required("admin")
def project_export_admin():
    return render_template("admin/project_export.html")


@roles_required("admin")
def project_export_workspace():
    with transaction_scope() as db:
        return render_template("admin/partials/project_export_workspace.html", **export_options(db))
