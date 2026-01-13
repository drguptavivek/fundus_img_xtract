from __future__ import annotations

from flask import render_template
from flask_login import current_user
from auth.roles import roles_required
from models import DirectImageUpload
from .encounterUtils import get_direct_image_summary
from utils.upload_eligibility import get_user_lab_unit_ids

from . import bp


@bp.route("/direct/view/<string:uuid_str>", methods=["GET"])
@roles_required("admin", "local_admin", "data_manager", "analytics_viewer")
def view_direct_image(uuid_str: str):
    # Use the utility function to get comprehensive summary (now scoped)
    summary = get_direct_image_summary(uuid_str, current_user)
    if not summary:
        from flask import abort
        abort(404, description="Direct upload not found or access denied")

    # Access control is handled by apply_scoping within get_direct_image_summary
    
    from flask import url_for

    image_url = url_for("media._imgForGradingByUUID", uuid_str=uuid_str)

    return render_template(
        "analytics/view_direct_upload.html",
        upload=summary['direct_image'],
        tasks=summary['tasks'],
        image_url=image_url,
    )
