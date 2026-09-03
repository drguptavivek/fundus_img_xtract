from __future__ import annotations

import logging
import os

from flask import current_app, jsonify, request

from auth.credentials import credential_authenticated
from auth.utils import get_client_ip
from db_transaction_manager import transaction_scope
from auth.decorators import token_auth_required
from services.mobile.auth_sessions import (
    MobileAuthError,
    MobileLoginRequest,
    RefreshTokenRequest,
    decode_access_claims_without_revocation,
    login_mobile_user,
    logout_mobile_session,
    reauthenticate_mobile_session,
    refresh_mobile_tokens,
    validate_access_session,
)
from utils.rate_limiter import auth_rate_limit, get_login_rate_limit_key, rate_limit

from . import mobile_api_bp

logger = logging.getLogger("api.mobile.auth")


@mobile_api_bp.route("/auth/login", methods=["POST"])
@credential_authenticated
@auth_rate_limit("10 per minute", key_func=get_login_rate_limit_key)
def login():
    payload = request.get_json(silent=True) or {}
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""
    device_id = (payload.get("device_id") or "").strip()
    device_name = (payload.get("device_name") or "").strip()
    enrolment_code = (payload.get("enrolment_code") or "").strip()
    platform = (payload.get("platform") or "").strip() or None

    if not username or not password or not device_id or not device_name:
        return jsonify({"error": "username, password, device_id, and device_name are required"}), 400
    captcha_error = require_web_captcha(platform, payload.get("captcha"))
    if captcha_error:
        return captcha_error

    try:
        with transaction_scope() as db:
            return jsonify(
                login_mobile_user(
                    db,
                    MobileLoginRequest(
                        username=username,
                        password=password,
                        device_id=device_id,
                        device_name=device_name,
                        ip_address=get_client_ip(),
                        enrolment_code=enrolment_code,
                        platform=platform,
                    ),
                )
            )
    except MobileAuthError as exc:
        return jsonify({"error": exc.code, "message": exc.message}), exc.status_code
    except RuntimeError as exc:
        if "JWT_SECRET" not in str(exc) and "secret configured" not in str(exc):
            raise
        current_app.logger.error("Mobile auth secret configuration error: %s", exc)
        return jsonify({"error": "server_configuration_error", "message": "Server configuration error"}), 500


@mobile_api_bp.route("/auth/refresh", methods=["POST"])
@credential_authenticated
@rate_limit("30 per minute")
def refresh():
    payload = request.get_json(silent=True) or {}
    refresh_token = payload.get("refresh_token") or ""
    device_id = (payload.get("device_id") or "").strip()
    if not refresh_token or not device_id:
        return jsonify({"error": "refresh_token and device_id are required"}), 400

    try:
        with transaction_scope() as db:
            return jsonify(refresh_mobile_tokens(db, RefreshTokenRequest(refresh_token=refresh_token, device_id=device_id)))
    except MobileAuthError as exc:
        return jsonify({"error": exc.code, "message": exc.message}), exc.status_code


def require_web_captcha(platform: str | None, captcha_input, *, consume: bool = True):
    """Browsers (``platform == "web"``) must solve the session CAPTCHA on
    sign-in, exactly as the web login form does; native apps are unchanged.
    ``consume=False`` peeks (the passkey lookup), leaving the CAPTCHA for the
    credential step. Returns an error response or ``None``."""
    if platform != "web":
        return None
    from utils.captcha import captcha_manager

    valid, message = captcha_manager.validate_captcha((captcha_input or "").strip(), consume=consume)
    if not valid:
        return jsonify({"error": "captcha_invalid", "message": message}), 400
    return None


@mobile_api_bp.route("/auth/reauth", methods=["POST"])
@token_auth_required
@auth_rate_limit("10 per minute", key_func=get_login_rate_limit_key)
def reauth():
    """Re-prove identity with the password on the current mobile session.

    Used after 30 idle minutes (``401 reauth_required``). Returns a fresh
    access token; the refresh token is unchanged. Web (grader) devices must
    re-authenticate with a passkey instead - the password path is refused
    for them so the policy holds server-side, not only in the UI.
    """
    payload = request.get_json(silent=True) or {}
    password = payload.get("password") or ""
    if not password:
        return jsonify({"error": "password_required", "message": "password is required"}), 400
    try:
        with transaction_scope() as db:
            context = validate_access_session(db, request.mobile_claims)
            from mobile_devices.service import device_platform

            if device_platform(db, user_id=context.user.id, device_id=context.session.device_id) == "web":
                return jsonify({
                    "error": "passkey_required",
                    "message": "Use your passkey to continue, or sign in again.",
                }), 403
            return jsonify(
                reauthenticate_mobile_session(
                    db, context=context, password=password, ip_address=get_client_ip()
                )
            )
    except MobileAuthError as exc:
        return jsonify({"error": exc.code, "message": exc.message}), exc.status_code


@mobile_api_bp.route("/auth/logout", methods=["POST"])
@credential_authenticated
@rate_limit("30 per minute")
def logout():
    payload = request.get_json(silent=True) or {}
    refresh_token = payload.get("refresh_token") or ""
    if not refresh_token:
        return jsonify({"error": "refresh_token is required"}), 400

    access_claims = _optional_access_claims()
    with transaction_scope() as db:
        logout_mobile_session(db, refresh_token=refresh_token, access_claims=access_claims)
        return ("", 204)


def _optional_access_claims() -> dict | None:
    jwt_secret = os.environ.get("JWT_SECRET")
    if not jwt_secret:
        return None
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    return decode_access_claims_without_revocation(auth_header.split(" ", 1)[1], jwt_secret)
