# direct_uploads/uploads.py

from flask import render_template, redirect, url_for, flash
from flask_login import current_user

from utils.env_loader import load_environment

from . import bp
from db_transaction_manager import get_db_session
from auth.roles import roles_required
from utils.rate_limiter import upload_rate_limit

from utils.upload_eligibility import get_user_uploadVerify_eligibility, get_user_lab_unit_ids_no_admin_override


load_environment()


@bp.route("/upload", methods=["GET"])
@roles_required("admin", "local_admin", "data_manager", "ophthalmologist", "resident", "optometrist", "fileUploader")
def upload_index():
    eligibility = get_user_uploadVerify_eligibility(current_user.id)
    return render_template("direct_uploads/index.html", eligibility=eligibility)


@bp.route("/direct/upload", methods=["GET"])
@roles_required("fileUploader")
@upload_rate_limit("60 per minute")  # Reduced to prevent abuse while allowing reasonable uploads
def upload():
    with get_db_session() as db_session:
        allowed_lab_units = get_user_lab_unit_ids_no_admin_override(current_user.id)
        if not allowed_lab_units:
            flash("You are not mapped to any lab units.", "warning")
            return redirect(url_for("home.index"))
        return render_template("direct_uploads/upload.html")
