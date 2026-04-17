from __future__ import annotations

import logging

from flask import jsonify, request
from sqlalchemy import func, select

from auth.decorators import token_auth_required
from auth.mobile_tokens import (
    create_mobile_session,
    find_session_by_refresh_token,
    mobile_auth_response,
    revoke_mobile_session,
    rotate_refresh_token,
    serialize_mobile_session,
    validate_mobile_session,
)
from auth.routes import (
    _is_ip_locked,
    _lock_ip,
    _lock_user,
    _recent_failed_by_ip,
    _recent_failed_by_username,
    _record_attempt,
    MAX_FAILS_PER_IP,
    MAX_FAILS_PER_USERNAME,
)
from auth.security import verify_password
from auth.utils import get_client_ip, utcnow
from db_transaction_manager import transaction_scope
from models import MobileAuthSession, User
from utils.log_sanitize import sanitize_log_value
from utils.rate_limiter import auth_rate_limit, rate_limit

from . import mobile_api_bp

logger = logging.getLogger("api.mobile.auth")


@mobile_api_bp.route("/auth/login", methods=["POST"])
@auth_rate_limit("10 per minute")
def login():
    payload = request.get_json(silent=True) or {}
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""
    device_id = (payload.get("device_id") or "").strip()
    device_name = (payload.get("device_name") or "").strip()
    ip = get_client_ip()

    if not username or not password or not device_id or not device_name:
        return jsonify({"error": "username, password, device_id, and device_name are required"}), 400

    with transaction_scope() as db:
        ip_locked, _ = _is_ip_locked(db, ip)
        if ip_locked:
            return jsonify({"error": "Too many attempts. IP is temporarily locked."}), 403

        recent_user_fails = _recent_failed_by_username(db, username)
        if recent_user_fails >= MAX_FAILS_PER_USERNAME:
            user = db.execute(select(User).where(func.lower(User.username) == func.lower(username))).scalar_one_or_none()
            if user:
                _lock_user(db, user)
            _record_attempt(db, username, ip, success=False)
            return jsonify({"error": "Too many attempts. User is temporarily locked."}), 403

        recent_ip_fails = _recent_failed_by_ip(db, ip)
        if recent_ip_fails >= MAX_FAILS_PER_IP:
            _lock_ip(db, ip)
            _record_attempt(db, username, ip, success=False)
            return jsonify({"error": "Too many attempts. IP is temporarily locked."}), 403

        user = db.execute(select(User).where(func.lower(User.username) == func.lower(username))).scalar_one_or_none()
        if user and user.is_locked_until:
            locked_until = user.is_locked_until
            if locked_until.tzinfo is None:
                locked_until = locked_until.replace(tzinfo=utcnow().tzinfo)
            if locked_until > utcnow():
                _record_attempt(db, username, ip, success=False)
                return jsonify({"error": "Too many attempts. User is temporarily locked."}), 403

        if user is None or not user.is_active or not verify_password(user.password_hash, password):
            _record_attempt(db, username, ip, success=False)
            if user and _recent_failed_by_username(db, username) >= MAX_FAILS_PER_USERNAME:
                _lock_user(db, user)
            if _recent_failed_by_ip(db, ip) >= MAX_FAILS_PER_IP:
                _lock_ip(db, ip)
            return jsonify({"error": "Invalid username or password"}), 401

        _record_attempt(db, username, ip, success=True)
        _mobile_session, access_token, refresh_token, scope = create_mobile_session(
            db,
            user,
            device_id=device_id,
            device_name=device_name,
        )
        logger.info(
            "Mobile login successful user=%s device_id=%s",
            sanitize_log_value(user.username),
            sanitize_log_value(device_id),
        )
        return jsonify(mobile_auth_response(user, access_token, refresh_token, scope))


@mobile_api_bp.route("/auth/refresh", methods=["POST"])
@rate_limit("30 per minute")
def refresh():
    payload = request.get_json(silent=True) or {}
    refresh_token = payload.get("refresh_token") or ""
    device_id = (payload.get("device_id") or "").strip()
    if not refresh_token or not device_id:
        return jsonify({"error": "refresh_token and device_id are required"}), 400

    with transaction_scope() as db:
        mobile_session = find_session_by_refresh_token(db, refresh_token)
        if not validate_mobile_session(mobile_session):
            return jsonify({"error": "Invalid refresh token"}), 401
        assert mobile_session is not None
        if mobile_session.device_id != device_id:
            return jsonify({"error": "Invalid device for refresh token"}), 401

        user = db.get(User, mobile_session.user_id)
        if user is None or not user.is_active:
            revoke_mobile_session(db, mobile_session)
            return jsonify({"error": "User is inactive"}), 403

        access_token, new_refresh_token, scope = rotate_refresh_token(db, mobile_session, user)
        return jsonify(mobile_auth_response(user, access_token, new_refresh_token, scope))


@mobile_api_bp.route("/auth/logout", methods=["POST"])
@rate_limit("30 per minute")
def logout():
    payload = request.get_json(silent=True) or {}
    refresh_token = payload.get("refresh_token") or ""
    if not refresh_token:
        return jsonify({"error": "refresh_token is required"}), 400

    with transaction_scope() as db:
        mobile_session = find_session_by_refresh_token(db, refresh_token)
        if mobile_session is None:
            return ("", 204)
        revoke_mobile_session(db, mobile_session)
        return ("", 204)


@mobile_api_bp.route("/auth/sessions", methods=["GET"])
@token_auth_required
def list_sessions():
    mobile_auth = getattr(request, "mobile_auth", {})
    user_id = mobile_auth.get("user_id")
    if not user_id:
        return jsonify({"error": "Invalid access token"}), 401

    with transaction_scope() as db:
        sessions = db.execute(
            select(MobileAuthSession)
            .where(MobileAuthSession.user_id == user_id)
            .order_by(MobileAuthSession.created_at.desc())
        ).scalars().all()
        current_session_id = mobile_auth.get("mobile_session_id")
        payload = []
        for item in sessions:
            row = serialize_mobile_session(item)
            row["current"] = item.id == current_session_id
            payload.append(row)
        return jsonify({"sessions": payload})


@mobile_api_bp.route("/auth/sessions/<session_id>", methods=["DELETE"])
@token_auth_required
def revoke_session(session_id: str):
    mobile_auth = getattr(request, "mobile_auth", {})
    user_id = mobile_auth.get("user_id")
    if not user_id:
        return jsonify({"error": "Invalid access token"}), 401

    with transaction_scope() as db:
        mobile_session = db.execute(
            select(MobileAuthSession)
            .where(MobileAuthSession.id == session_id)
            .where(MobileAuthSession.user_id == user_id)
        ).scalar_one_or_none()
        if mobile_session is None:
            return ("", 204)
        revoke_mobile_session(db, mobile_session)
        return ("", 204)
