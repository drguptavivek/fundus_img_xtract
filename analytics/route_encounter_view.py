from __future__ import annotations

from flask import render_template, url_for

from auth.roles import roles_required

from . import bp


@bp.route("/encounter/view/<int:encounter_id>", methods=["GET"])
@roles_required("admin", "local_admin", "data_manager", "analytics_viewer")
def view_encounter(encounter_id: int):
    return render_template(
        "encounter_viewer/page.html",
        viewer_endpoint=url_for("fundus_api.encounter_viewer_encounter", encounter_id=encounter_id),
        back_url=url_for("analytics.encounter_results"),
        back_label="Encounters",
    )
