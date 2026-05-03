from __future__ import annotations

from flask import jsonify, request

from auth.decorators import token_auth_required
from db_transaction_manager import transaction_scope
from services.mobile.auth_sessions import get_mobile_session_payload, mobile_sessions_collection, revoke_user_mobile_session

from . import mobile_api_bp


@mobile_api_bp.route("/sessions", methods=["GET"])
@token_auth_required
def list_user_sessions():
    mobile_auth = getattr(request, "mobile_auth", {})
    user_id = mobile_auth.get("user_id")
    if not user_id:
        return jsonify({"error": "Invalid access token"}), 401

    with transaction_scope() as db:
        return jsonify(mobile_sessions_collection(db, user_id=user_id, current_session_id=mobile_auth.get("mobile_session_id")))


@mobile_api_bp.route("/sessions/<session_id>", methods=["GET"])
@token_auth_required
def get_user_session(session_id: str):
    mobile_auth = getattr(request, "mobile_auth", {})
    user_id = mobile_auth.get("user_id")
    if not user_id:
        return jsonify({"error": "Invalid access token"}), 401

    with transaction_scope() as db:
        payload = get_mobile_session_payload(
            db,
            user_id=user_id,
            session_id=session_id,
            current_session_id=mobile_auth.get("mobile_session_id"),
        )
        if payload is None:
            return jsonify({"error": "not_found"}), 404
        return jsonify(payload)


@mobile_api_bp.route("/sessions/<session_id>/revoke", methods=["POST"])
@token_auth_required
def revoke_user_session(session_id: str):
    mobile_auth = getattr(request, "mobile_auth", {})
    user_id = mobile_auth.get("user_id")
    if not user_id:
        return jsonify({"error": "Invalid access token"}), 401

    with transaction_scope() as db:
        revoked = revoke_user_mobile_session(
            db,
            user_id=user_id,
            session_id=session_id,
            current_session_id=mobile_auth.get("mobile_session_id"),
            access_claims=getattr(request, "mobile_claims", None),
        )
        return jsonify({"session_id": session_id, "revoked": revoked})
