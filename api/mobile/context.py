from __future__ import annotations

from flask import jsonify, request
from sqlalchemy import select

from auth.decorators import token_auth_required
from auth.mobile_tokens import build_mobile_scope
from db_transaction_manager import transaction_scope
from field_workbench.service import list_projects as list_field_projects
from models import User

from . import mobile_api_bp


@mobile_api_bp.route("/context/me", methods=["GET"])
@token_auth_required
def get_mobile_context():
    mobile_auth = getattr(request, "mobile_auth", {})
    user_id = mobile_auth.get("user_id")
    if not user_id:
        return jsonify({"error": "Invalid access token"}), 401

    with transaction_scope() as db:
        user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
        if user is None or not user.is_active:
            return jsonify({"error": "User is inactive"}), 403
        scope = build_mobile_scope(db, user)
        # Projects carry the field dimension the base scope has never had: which
        # projects this user may work in and which AI workflows each enables, so
        # the client can hide an action rather than discover a 409 by pressing it.
        projects = list_field_projects(db, user=user)
        return jsonify(
            {
                "projects": [project.to_dict() for project in projects],
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "full_name": user.full_name,
                    "hospital_id": user.hospital_id,
                },
                "hospital": scope["hospital"],
                "lab_units": scope["lab_units"],
                "allowed_disease_ids": scope["allowed_disease_ids"],
                "roles": scope["roles"],
                "token_shape": {
                    "access_token": {
                        "format": "JWT",
                        "algorithm": "HS256",
                        "claims": [
                            "sub",
                            "typ",
                            "jti",
                            "mobile_session_id",
                            "hospital_id",
                            "allowed_lab_unit_ids",
                            "allowed_disease_ids",
                            "roles",
                            "iat",
                            "exp",
                        ],
                    },
                    "refresh_token": {
                        "format": "opaque",
                        "storage": "hashed_server_side",
                    },
                },
            }
        )
