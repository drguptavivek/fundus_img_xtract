from __future__ import annotations

from flask import current_app, jsonify, request

from auth.decorators import token_auth_required
from db_transaction_manager import transaction_scope
from services.uploads import (
    MobileUploadError,
    create_mobile_upload,
    get_mobile_direct_upload_thumbnail,
    get_mobile_upload_inference,
    get_mobile_upload_status,
    get_mobile_upload_status_by_idempotency_key,
    retry_mobile_upload_inference,
    run_mobile_upload_post_commit,
)
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
            status_code = 200 if payload.pop("_replayed", False) else 201
            post_commit = payload.pop("_post_commit", None)
        run_mobile_upload_post_commit(current_app, post_commit)
        return jsonify(payload), status_code
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


@mobile_api_bp.route("/uploads/by-idempotency-key/<idempotency_key>", methods=["GET"])
@token_auth_required
def upload_status_by_idempotency_key(idempotency_key: str):
    user_id = _mobile_user_id()
    if not user_id:
        return jsonify({"error": "Invalid access token"}), 401
    try:
        with transaction_scope() as db:
            return jsonify(
                get_mobile_upload_status_by_idempotency_key(
                    db=db,
                    user_id=user_id,
                    idempotency_key=idempotency_key,
                )
            )
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


@mobile_api_bp.route("/uploads/<upload_token>/inference/retry", methods=["POST"])
@token_auth_required
def retry_upload_inference(upload_token: str):
    user_id = _mobile_user_id()
    if not user_id:
        return jsonify({"error": "Invalid access token"}), 401
    payload = request.get_json(silent=True) or {}
    task_ids = payload.get("task_ids")
    if task_ids is not None:
        if not isinstance(task_ids, list):
            return jsonify({"error": "invalid_task_ids", "message": "task_ids must be a list of task IDs."}), 400
        try:
            task_ids = [int(task_id) for task_id in task_ids]
        except (TypeError, ValueError):
            return jsonify({"error": "invalid_task_ids", "message": "task_ids must contain integer task IDs."}), 400
    try:
        with transaction_scope() as db:
            payload = retry_mobile_upload_inference(
                db=db,
                user_id=user_id,
                upload_token=upload_token,
                requested_task_ids=task_ids,
            )
            return jsonify(payload), 202
    except MobileUploadError as exc:
        return jsonify({"error": exc.code, "message": exc.message}), exc.status_code


@mobile_api_bp.route("/uploads/<upload_token>/images/<image_uuid>/thumbnail", methods=["GET"])
@token_auth_required
def upload_image_thumbnail(upload_token: str, image_uuid: str):
    user_id = _mobile_user_id()
    if not user_id:
        return jsonify({"error": "Invalid access token"}), 401
    try:
        with transaction_scope() as db:
            return get_mobile_direct_upload_thumbnail(
                db=db,
                user_id=user_id,
                upload_token=upload_token,
                image_uuid=image_uuid,
            )
    except MobileUploadError as exc:
        return jsonify({"error": exc.code, "message": exc.message}), exc.status_code


def _mobile_user_id() -> int | None:
    mobile_auth = getattr(request, "mobile_auth", {})
    return mobile_auth.get("user_id")
