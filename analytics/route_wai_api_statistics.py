"""WAI API statistics analytics page."""

from __future__ import annotations

from flask import render_template

from auth.roles import roles_required

from . import bp


@bp.route("/wai-api-statistics", methods=["GET"])
@roles_required("admin", "local_admin", "verifier", "data_manager", "analytics_viewer", "optometrist", "ophthalmologist", "field_optometrist", "field_ophthalmologist")
def wai_api_statistics() -> str:
    return render_template("analytics/wai_api_statistics.html")
