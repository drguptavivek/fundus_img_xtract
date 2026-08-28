# direct_uploads/uploads.py

from flask import render_template, redirect, request, url_for, flash
from flask_login import current_user

from utils.env_loader import load_environment

from . import bp
from db_transaction_manager import get_db_session
from auth.roles import roles_required
from utils.rate_limiter import upload_rate_limit

from utils.upload_eligibility import get_user_uploadVerify_eligibility


load_environment()


@bp.route("/upload", methods=["GET"])
@roles_required(
    "admin",
    "local_admin",
    "data_manager",
    "ophthalmologist",
    "optometrist",
    "fileUploader",
)
def upload_index():
    eligibility = get_user_uploadVerify_eligibility(current_user.id)
    return render_template("direct_uploads/index.html", eligibility=eligibility)


@bp.route("/direct/upload", methods=["GET"])
@roles_required("fileUploader")
@upload_rate_limit("60 per minute")  # Reduced to prevent abuse while allowing reasonable uploads
def upload():
    with get_db_session() as db_session:
        from upload_profiles.service import get_user_upload_options_for_kind

        options = get_user_upload_options_for_kind(db_session, current_user.id, "direct_image")
        if not options.profiles:
            flash("You are not mapped to any lab units.", "warning")
            return redirect(url_for("home.index"))
        return render_template(
            "direct_uploads/upload.html",
            selected_project_id=request.args.get("project_id", type=int),
        )
