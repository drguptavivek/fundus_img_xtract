from __future__ import annotations

from flask import render_template
from sqlalchemy.orm import selectinload

from auth.roles import roles_required
from models import DirectImageUpload, Session

from . import bp


@bp.route("/direct/view/<uuid_str>", methods=["GET"])
@roles_required("admin", "data_manager", "optometrist")
def view_upload(uuid_str: str):
    db = Session()
    try:
        upload = (
            db.query(DirectImageUpload)
            .options(
                selectinload(DirectImageUpload.hospital),
                selectinload(DirectImageUpload.lab_unit),
                selectinload(DirectImageUpload.camera),
                selectinload(DirectImageUpload.disease),
                selectinload(DirectImageUpload.area),
                selectinload(DirectImageUpload.uploader),
            )
            .filter(DirectImageUpload.uuid == uuid_str)
            .first()
        )
        if not upload:
            from flask import abort
            abort(404)

        from flask import url_for

        image_url = url_for("media._imgForGradingByUUID", uuid_str=upload.uuid)

        return render_template(
            "analytics/view_direct_upload.html",
            upload=upload,
            image_url=image_url,
        )
    finally:
        db.close()
