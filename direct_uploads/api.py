from flask import jsonify
from flask_login import login_required, current_user
from sqlalchemy import select
from . import bp
from db_transaction_manager import get_db_session
from utils.rate_limiter import api_rate_limit
from models import User, LabUnit
from auth.roles import global_uploader_or_project_assignment_required
from upload_profiles.service import get_user_upload_options_for_kind

@bp.route("/api/lab-units/<int:user_id>", methods=["GET"])
@login_required
@global_uploader_or_project_assignment_required("direct_image")
@api_rate_limit("120 per minute")
def get_lab_units(user_id):
    with get_db_session() as db:
        user = db.get(User, user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404
        # Only allow access if caller is requesting self OR has admin/local_admin role
        if current_user.id != user_id and not current_user.has_role("admin", "local_admin"):
            return jsonify({"error": "Forbidden"}), 403

        options = get_user_upload_options_for_kind(db, current_user.id, "direct_image")
        return jsonify([{"id": item["id"], "name": item["name"]} for item in options.lab_units])

@bp.route("/api/hospital/<int:lab_unit_id>", methods=["GET"])
@login_required
@global_uploader_or_project_assignment_required("direct_image")
@api_rate_limit("120 per minute")
def get_hospital(lab_unit_id):
    with get_db_session() as db:
        options = get_user_upload_options_for_kind(db, current_user.id, "direct_image")
        if lab_unit_id not in {item["id"] for item in options.lab_units}:
            return jsonify({"error": "Forbidden"}), 403

        lu = db.get(LabUnit, lab_unit_id)
        if not lu:
            return jsonify({"error": "Lab unit not found"}), 404
        return jsonify({"id": lu.hospital.id, "name": lu.hospital.name})
