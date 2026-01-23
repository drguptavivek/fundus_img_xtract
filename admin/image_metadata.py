from flask import current_app, flash, redirect, render_template, request, url_for
from flask_login import login_required
from auth.roles import roles_required
from db_transaction_manager import get_db_session
from models import DirectImageUpload, EncounterFile, ImageMetadata, ImagePiiVerification
from sqlalchemy import func
from utils.image_metadata_backfill import enqueue_image_metadata_backfill
from utils.log_sanitize import sanitize_log_value


@login_required
@roles_required("admin", "data_manager")
def image_metadata_admin():
    with get_db_session() as db:
        encounter_total = db.query(func.count(EncounterFile.id)).scalar() or 0
        direct_total = db.query(func.count(DirectImageUpload.id)).scalar() or 0
        edited_total = (
            db.query(func.count(DirectImageUpload.id))
            .filter(DirectImageUpload.edited_filename.isnot(None))
            .scalar()
            or 0
        )
        metadata_total = db.query(func.count(ImageMetadata.id)).scalar() or 0
        pii_total = db.query(func.count(ImagePiiVerification.id)).scalar() or 0

    totals = {
        "encounter": int(encounter_total),
        "direct": int(direct_total),
        "edited": int(edited_total),
        "metadata": int(metadata_total),
        "pii": int(pii_total),
    }

    return render_template("admin/image_metadata.html", totals=totals)


@login_required
@roles_required("admin", "data_manager")
def image_metadata_backfill():
    limit = request.form.get("limit", type=int)
    enqueue_image_metadata_backfill(current_app._get_current_object(), limit=limit)
    flash("Image metadata backfill queued.", "info")
    return redirect(url_for("admin.image_metadata_admin"))
