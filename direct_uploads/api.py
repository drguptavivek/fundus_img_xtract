from flask import jsonify
from flask_login import login_required, current_user
from sqlalchemy import select
from . import bp
from db_transaction_manager import get_db_session
from utils.rate_limiter import api_rate_limit
from models import User, LabUnit
from auth.roles import roles_required
from utils.upload_eligibility import get_user_lab_unit_ids_no_admin_override

@bp.route("/api/lab-units/<int:user_id>", methods=["GET"])
@login_required
@roles_required("admin", "local_admin", "fileUploader", "optometrist", "data_manager")
@api_rate_limit("120 per minute")
def get_lab_units(user_id):
    with get_db_session() as db:
        user = db.get(User, user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404
        allowed_lab_unit_ids = get_user_lab_unit_ids_no_admin_override(current_user.id)
        if not allowed_lab_unit_ids:
            return jsonify([])

        # Only allow access if caller is requesting self OR has admin/local_admin role
        if current_user.id != user_id and not current_user.has_role("admin", "local_admin"):
            return jsonify({"error": "Forbidden"}), 403

        lab_units = (
            db.query(LabUnit)
            .filter(
                LabUnit.id.in_(allowed_lab_unit_ids),
                LabUnit.id.in_([lu.id for lu in user.lab_units]),
            )
            .order_by(LabUnit.name.asc())
            .all()
        )
        return jsonify([{"id": lu.id, "name": lu.name} for lu in lab_units])

@bp.route("/api/hospital/<int:lab_unit_id>", methods=["GET"])
@login_required
@roles_required("admin", "local_admin", "fileUploader", "optometrist", "data_manager")
@api_rate_limit("120 per minute")
def get_hospital(lab_unit_id):
    with get_db_session() as db:
        allowed_lab_unit_ids = get_user_lab_unit_ids_no_admin_override(current_user.id)
        if lab_unit_id not in allowed_lab_unit_ids:
            return jsonify({"error": "Forbidden"}), 403

        lu = db.get(LabUnit, lab_unit_id)
        if not lu:
            return jsonify({"error": "Lab unit not found"}), 404
        return jsonify({"id": lu.hospital.id, "name": lu.hospital.name})
