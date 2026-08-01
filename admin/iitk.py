"""Backward-compatible redirects for the retired IITK configuration page."""
from flask import redirect, url_for

from auth.roles import roles_required


@roles_required("admin", "local_admin", "data_manager")
def iitk_admin():
    return redirect(url_for("admin.upload_projects_admin"))


@roles_required("admin", "local_admin", "data_manager")
def iitk_workspace():
    return redirect(url_for("admin.upload_projects_admin"))
