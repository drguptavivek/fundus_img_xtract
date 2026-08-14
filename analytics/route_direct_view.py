from __future__ import annotations

from flask import render_template, url_for

from auth.roles import roles_required

from . import bp


@bp.route("/direct/view/<string:uuid_str>", methods=["GET"])
@roles_required("admin", "local_admin", "data_manager", "analytics_viewer")
def view_direct_image(uuid_str: str):
    return render_template(
        "encounter_viewer/page.html",
        viewer_endpoint=url_for("fundus_api.encounter_viewer_image", image_uuid=uuid_str),
        back_url=url_for("analytics.images_without_tasks"),
        back_label="Images",
    )
