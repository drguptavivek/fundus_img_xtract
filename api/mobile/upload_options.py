from __future__ import annotations

from flask import jsonify, request
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from auth.decorators import token_auth_required
from db_transaction_manager import transaction_scope
from models import User
from upload_profiles.service import UploadOptions, filter_upload_options, get_user_upload_options

from . import mobile_api_bp


@mobile_api_bp.route("/upload-options", methods=["GET"])
@token_auth_required
def get_mobile_upload_options():
    mobile_auth = getattr(request, "mobile_auth", {})
    user_id = mobile_auth.get("user_id")
    if not user_id:
        return jsonify({"error": "Invalid access token"}), 401

    filters, error_response = _parse_filters()
    if error_response is not None:
        return error_response

    with transaction_scope() as db:
        user = db.execute(
            select(User)
            .options(selectinload(User.roles))
            .where(User.id == user_id)
        ).scalar_one_or_none()
        if user is None or not user.is_active:
            return jsonify({"error": "User is inactive"}), 403
        if not user.has_role("fileUploader"):
            return jsonify({"error": "Forbidden"}), 403

        options = get_user_upload_options(db, user.id)
        options = filter_upload_options(db, options, **filters)
        return jsonify(_serialize_upload_options(options))


def _parse_filters():
    try:
        return {
            "disease_id": _optional_int("disease_id"),
            "disease_name": request.args.get("disease_name"),
            "project_id": _optional_int("project_id"),
            "lab_unit_id": _optional_int("lab_unit_id"),
        }, None
    except ValueError as exc:
        return {}, (jsonify({"error": str(exc)}), 400)


def _optional_int(name: str) -> int | None:
    value = request.args.get(name)
    if value is None or value == "":
        return None
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if parsed <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return parsed


def _serialize_upload_options(options: UploadOptions) -> dict:
    return {
        "projects": options.projects,
        "lab_units": options.lab_units,
        "diseases": options.diseases,
        "cameras": options.cameras,
        "areas": options.areas,
        "profiles": options.profiles,
    }
