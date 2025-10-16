from __future__ import annotations

from flask import render_template
from flask_login import current_user
from auth.roles import roles_required
from models import DirectImageUpload, Session
from .encounterUtils import get_direct_image_summary
from utils.upload_eligibility import get_user_lab_unit_ids

from . import bp


@bp.route("/direct/view/<uuid_str>", methods=["GET"])
@roles_required("admin", "data_manager")
def view_upload(uuid_str: str):
    # Use the utility function to get comprehensive summary
    summary = get_direct_image_summary(uuid_str)
    if not summary:
        from flask import abort
        abort(404)

    # Check if the user has access to the lab unit this direct upload belongs to
    is_admin_like = current_user.has_role("admin", "data_manager")
    user_lab_unit_ids = get_user_lab_unit_ids(current_user.id)
    
    direct_image = summary.get('direct_image', {})
    lab_unit_id = direct_image.get('lab_unit_id')
    
    if not is_admin_like and lab_unit_id and lab_unit_id not in user_lab_unit_ids:
        from flask import abort
        abort(403, description="Access denied to this lab unit")
    
    from flask import url_for

    image_url = url_for("media._imgForGradingByUUID", uuid_str=uuid_str)

    return render_template(
        "analytics/view_direct_upload.html",
        upload=summary['direct_image'],
        tasks=summary['tasks'],
        image_url=image_url,
    )
