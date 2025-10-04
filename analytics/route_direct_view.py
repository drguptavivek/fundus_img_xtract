from __future__ import annotations

from flask import render_template
from sqlalchemy.orm import selectinload

from auth.roles import roles_required
from models import DirectImageUpload, Session
from .encounterUtils import get_direct_image_summary

from . import bp


@bp.route("/direct/view/<uuid_str>", methods=["GET"])
@roles_required("admin", "data_manager", "optometrist")
def view_upload(uuid_str: str):
    # Use the utility function to get comprehensive summary
    summary = get_direct_image_summary(uuid_str)
    if not summary:
        from flask import abort
        abort(404)

    from flask import url_for

    image_url = url_for("media._imgForGradingByUUID", uuid_str=uuid_str)

    return render_template(
        "analytics/view_direct_upload.html",
        upload=summary['direct_image'],
        tasks=summary['tasks'],
        image_url=image_url,
    )
