from flask import jsonify
from flask_login import login_required, current_user
from sqlalchemy import select
from . import bp
from .utils import with_session
from models import User, LabUnit

@bp.route("/api/lab-units/<int:user_id>", methods=["GET"])
@login_required
def get_lab_units(user_id):
    with with_session() as db:
        user = db.get(User, user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404
        if not (current_user.has_role('admin', 'data_manager') or current_user.id == user_id):
            return jsonify({"error": "Forbidden"}), 403
        return jsonify([{"id": lu.id, "name": lu.name} for lu in user.lab_units])

@bp.route("/api/hospital/<int:lab_unit_id>", methods=["GET"])
@login_required
def get_hospital(lab_unit_id):
    with with_session() as db:
        lu = db.get(LabUnit, lab_unit_id)
        if not lu:
            return jsonify({"error": "Lab unit not found"}), 404
        return jsonify({"id": lu.hospital.id, "name": lu.hospital.name})
