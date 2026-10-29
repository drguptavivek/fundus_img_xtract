"""Passkey step-up authentication for the current web session."""

import hmac
import logging
import time

from flask import jsonify, request, session, url_for
from flask_login import current_user, login_required

from api import api_bp
from db_transaction_manager import transaction_scope
from models import User
from passkeys import service as passkeys
from passkeys.service import PasskeyError
from utils.rate_limiter import rate_limit
from utils.security_middleware import is_safe_url
from auth.utils import get_client_ip
from utils.log_sanitize import sanitize_log_value

_SESSION_KEY = "web_reauth_passkey"
_logger = logging.getLogger("auth")


@api_bp.route("/auth/reauth/passkey/options", methods=["POST"])
@login_required
@rate_limit("20 per minute")
def web_reauth_passkey_options():
    session.pop(_SESSION_KEY, None)
    try:
        with transaction_scope() as db:
            user = db.get(User, int(current_user.id))
            if user is None:
                return jsonify(error="unauthorized", message="Sign in again."), 401
            ceremony = passkeys.begin_assertion(db, user=user)
        session[_SESSION_KEY] = {"user_id": int(current_user.id), "challenge_id": ceremony["challenge_id"]}
        return jsonify(ceremony)
    except PasskeyError as exc:
        return jsonify(error=exc.code, message=exc.message), exc.status_code


@api_bp.route("/auth/reauth/passkey/verify", methods=["POST"])
@login_required
@rate_limit("20 per minute")
def web_reauth_passkey_verify():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error="invalid_request", message="A JSON object is required."), 400
    challenge_id = payload.get("challenge_id")
    credential = payload.get("credential")
    pending = session.pop(_SESSION_KEY, None)
    if (not isinstance(pending, dict) or pending.get("user_id") != int(current_user.id)
            or not isinstance(challenge_id, str)
            or not hmac.compare_digest(str(pending.get("challenge_id", "")).encode(), challenge_id.encode())):
        return jsonify(error="challenge_mismatch", message="Start passkey confirmation again."), 400
    if not isinstance(credential, dict):
        return jsonify(error="credential_required", message="A passkey credential is required."), 400
    try:
        with transaction_scope() as db:
            user = db.get(User, int(current_user.id))
            if user is None:
                return jsonify(error="unauthorized", message="Sign in again."), 401
            passkeys.complete_assertion(db, user=user, challenge_id=challenge_id, credential=credential)
    except PasskeyError as exc:
        _logger.warning("Passkey re-authentication failed - UserID: %s, IP: %s, code: %s", sanitize_log_value(current_user.id), sanitize_log_value(get_client_ip()), sanitize_log_value(exc.code))
        return jsonify(error=exc.code, message=exc.message), exc.status_code
    session["last_sudo_time"] = int(time.time())
    _logger.info("Passkey re-authentication successful - UserID: %s, IP: %s", sanitize_log_value(current_user.id), sanitize_log_value(get_client_ip()))
    requested_next = payload.get("next")
    try:
        next_url = requested_next if isinstance(requested_next, str) and is_safe_url(requested_next) else url_for("homepage")
    except ValueError:
        next_url = url_for("homepage")
    return jsonify(success=True, redirect_url=next_url)
