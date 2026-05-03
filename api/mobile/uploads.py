from __future__ import annotations

from flask import jsonify, request

from auth.decorators import token_auth_required
from db_transaction_manager import transaction_scope
from services.uploads import MobileUploadError, create_mobile_upload, get_mobile_upload_inference, get_mobile_upload_status
from upload_profiles.service import UploadProfileError

from . import mobile_api_bp


@mobile_api_bp.route("/uploads", methods=["POST"])
@token_auth_required
def create_upload():
    user_id = _mobile_user_id()
    if not user_id:
        return jsonify({"error": "Invalid access token"}), 401
    try:
        with transaction_scope() as db:
            payload = create_mobile_upload(
                db=db,
                user_id=user_id,
                form=request.form,
                files=request.files,
                remote_addr=request.remote_addr,
            )
            return jsonify(payload), 201
    except UploadProfileError as exc:
        return jsonify({"error": exc.code, "message": exc.message}), 403
    except MobileUploadError as exc:
        return jsonify({"error": exc.code, "message": exc.message}), exc.status_code


@mobile_api_bp.route("/uploads/<upload_token>", methods=["GET"])
@token_auth_required
def upload_status(upload_token: str):
    user_id = _mobile_user_id()
    if not user_id:
        return jsonify({"error": "Invalid access token"}), 401
    try:
        with transaction_scope() as db:
            return jsonify(get_mobile_upload_status(db=db, user_id=user_id, upload_token=upload_token))
    except MobileUploadError as exc:
        return jsonify({"error": exc.code, "message": exc.message}), exc.status_code


@mobile_api_bp.route("/uploads/<upload_token>/inference", methods=["GET"])
@token_auth_required
def upload_inference(upload_token: str):
    user_id = _mobile_user_id()
    if not user_id:
        return jsonify({"error": "Invalid access token"}), 401
    try:
        with transaction_scope() as db:
            return jsonify(get_mobile_upload_inference(db=db, user_id=user_id, upload_token=upload_token))
    except MobileUploadError as exc:
        return jsonify({"error": exc.code, "message": exc.message}), exc.status_code


def _mobile_user_id() -> int | None:
    mobile_auth = getattr(request, "mobile_auth", {})
    return mobile_auth.get("user_id")
