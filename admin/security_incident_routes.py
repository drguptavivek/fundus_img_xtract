"""Admin security incident page; data comes from the JSON/HTMX API."""
from flask import render_template
from auth.roles import roles_required
from . import admin_bp


@admin_bp.get("/security/incidents")
@roles_required("admin")
def security_incidents():
    return render_template("admin/security_incidents.html")
