"""Passkey (WebAuthn) endpoints on the mobile bearer-token surface.

Registration requires a recently password-authenticated session (the login
itself, or a password re-authentication within the last 30 minutes) so a
stolen access token cannot enrol a new credential. Assertion is the
biometric re-authentication path: a verified assertion mints a fresh access
token exactly like the password route.
"""
from __future__ import annotations

from flask import jsonify, request

from auth.credentials import credential_authenticated
from auth.decorators import token_auth_required
from auth.utils import get_client_ip, utcnow
from db_transaction_manager import transaction_scope
from passkeys import service as passkey_service
from passkeys.models import MobilePasskey  # noqa: F401 - registers the table with the metadata
from passkeys.service import PasskeyError
from services.mobile.auth_sessions import (
    MobileAuthError,
    MobileLoginRequest,
    login_mobile_user_with_passkey,
    mark_reauthenticated,
    mobile_login_gate,
    validate_access_session,
)
from utils.rate_limiter import auth_rate_limit, get_login_rate_limit_key, rate_limit

from . import mobile_api_bp

REGISTRATION_MAX_AUTH_AGE_SECONDS = 30 * 60


def _error(exc: PasskeyError):
    return jsonify({"error": exc.code, "message": exc.message}), exc.status_code


def _context(db):
    return validate_access_session(db, request.mobile_claims)


def _require_recent_password(context):
    authenticated_at = context.authenticated_at
    if authenticated_at is None:
        raise PasskeyError("Sign in with your password before adding a passkey.", code="reauth_required", status_code=401)
    if authenticated_at.tzinfo is None:
        authenticated_at = authenticated_at.replace(tzinfo=utcnow().tzinfo)
    if (utcnow() - authenticated_at).total_seconds() > REGISTRATION_MAX_AUTH_AGE_SECONDS:
        raise PasskeyError("Confirm your password before adding a passkey.", code="reauth_required", status_code=401)


@mobile_api_bp.route("/auth/passkeys", methods=["GET"])
@token_auth_required
def list_passkeys():
    with transaction_scope() as db:
        context = _context(db)
        return jsonify({"passkeys": [item.to_dict() for item in passkey_service.list_passkeys(db, user_id=context.user.id)]})


@mobile_api_bp.route("/auth/passkeys/register/options", methods=["POST"])
@token_auth_required
@rate_limit("10 per minute")
def passkey_register_options():
    try:
        with transaction_scope() as db:
            context = _context(db)
            _require_recent_password(context)
            return jsonify(passkey_service.begin_registration(db, user=context.user))
    except PasskeyError as exc:
        return _error(exc)
    except MobileAuthError as exc:
        return jsonify({"error": exc.code, "message": exc.message}), exc.status_code


@mobile_api_bp.route("/auth/passkeys/register/verify", methods=["POST"])
@token_auth_required
@rate_limit("10 per minute")
def passkey_register_verify():
    payload = request.get_json(silent=True) or {}
    credential = payload.get("credential")
    if not isinstance(credential, dict):
        return jsonify({"error": "credential_required", "message": "credential is required."}), 400
    try:
        with transaction_scope() as db:
            context = _context(db)
            _require_recent_password(context)
            passkey = passkey_service.complete_registration(
                db,
                user=context.user,
                challenge_id=str(payload.get("challenge_id") or ""),
                credential=credential,
                label=payload.get("label"),
                device_id=context.session.device_id,
            )
            return jsonify({"passkey": passkey.to_dict()}), 201
    except PasskeyError as exc:
        return _error(exc)
    except MobileAuthError as exc:
        return jsonify({"error": exc.code, "message": exc.message}), exc.status_code


@mobile_api_bp.route("/auth/passkeys/reauth/options", methods=["POST"])
@token_auth_required
@rate_limit("20 per minute")
def passkey_reauth_options():
    try:
        with transaction_scope() as db:
            context = _context(db)
            return jsonify(passkey_service.begin_assertion(db, user=context.user))
    except PasskeyError as exc:
        return _error(exc)
    except MobileAuthError as exc:
        return jsonify({"error": exc.code, "message": exc.message}), exc.status_code


@mobile_api_bp.route("/auth/passkeys/reauth/verify", methods=["POST"])
@token_auth_required
@rate_limit("20 per minute")
def passkey_reauth_verify():
    payload = request.get_json(silent=True) or {}
    credential = payload.get("credential")
    if not isinstance(credential, dict):
        return jsonify({"error": "credential_required", "message": "credential is required."}), 400
    try:
        with transaction_scope() as db:
            context = _context(db)
            passkey_service.complete_assertion(
                db,
                user=context.user,
                challenge_id=str(payload.get("challenge_id") or ""),
                credential=credential,
            )
            return jsonify(mark_reauthenticated(db, context=context, ip_address=get_client_ip(), method="passkey"))
    except PasskeyError as exc:
        return _error(exc)
    except MobileAuthError as exc:
        return jsonify({"error": exc.code, "message": exc.message}), exc.status_code


@mobile_api_bp.route("/auth/passkeys/<int:passkey_id>", methods=["DELETE"])
@token_auth_required
@rate_limit("10 per minute")
def passkey_delete(passkey_id: int):
    with transaction_scope() as db:
        context = _context(db)
        if not passkey_service.delete_passkey(db, user_id=context.user.id, passkey_id=passkey_id):
            return jsonify({"error": "not_found", "message": "Passkey not found."}), 404
    return ("", 204)


# --------------------------------------------------------------------------- #
# Passkey sign-in (no bearer yet): username -> assertion -> tokens
# --------------------------------------------------------------------------- #


def _no_passkey():
    return jsonify({"error": "no_passkey", "message": "No passkey is registered for this username."}), 404


@mobile_api_bp.route("/auth/passkeys/login/options", methods=["POST"])
@credential_authenticated
@auth_rate_limit("10 per minute", key_func=get_login_rate_limit_key)
def passkey_login_options():
    """WebAuthn request options for a username. Same lockouts as the password
    login; unknown users and users without a passkey answer identically."""
    payload = request.get_json(silent=True) or {}
    username = (payload.get("username") or "").strip()
    if not username:
        return jsonify({"error": "username_required", "message": "username is required"}), 400
    try:
        with transaction_scope() as db:
            user = mobile_login_gate(db, username=username, ip=get_client_ip())
            if user is None:
                return _no_passkey()
            try:
                return jsonify(passkey_service.begin_assertion(db, user=user))
            except PasskeyError:
                return _no_passkey()
    except MobileAuthError as exc:
        return jsonify({"error": exc.code, "message": exc.message}), exc.status_code


@mobile_api_bp.route("/auth/passkeys/login/verify", methods=["POST"])
@credential_authenticated
@auth_rate_limit("10 per minute", key_func=get_login_rate_limit_key)
def passkey_login_verify():
    """Verify the assertion and open a mobile session (tokens), exactly as a
    password login would after the credential check."""
    payload = request.get_json(silent=True) or {}
    username = (payload.get("username") or "").strip()
    device_id = (payload.get("device_id") or "").strip()
    device_name = (payload.get("device_name") or "").strip()
    credential = payload.get("credential")
    challenge_id = str(payload.get("challenge_id") or "")
    if not username or not device_id or not device_name or not isinstance(credential, dict):
        return jsonify({"error": "invalid_request", "message": "username, device_id, device_name and credential are required"}), 400
    ip = get_client_ip()
    try:
        with transaction_scope() as db:
            user = mobile_login_gate(db, username=username, ip=ip)
            if user is None:
                return jsonify({"error": "invalid_credentials", "message": "Passkey sign-in failed"}), 401
            try:
                passkey_service.complete_assertion(db, user=user, challenge_id=challenge_id, credential=credential)
            except PasskeyError:
                from auth.routes import _record_attempt

                _record_attempt(db, username, ip, success=False)
                return jsonify({"error": "invalid_credentials", "message": "Passkey sign-in failed"}), 401
            return jsonify(
                login_mobile_user_with_passkey(
                    db,
                    MobileLoginRequest(
                        username=username,
                        password="",
                        device_id=device_id,
                        device_name=device_name,
                        ip_address=ip,
                        enrolment_code=(payload.get("enrolment_code") or "").strip(),
                        platform=(payload.get("platform") or "").strip() or None,
                    ),
                    user=user,
                )
            )
    except MobileAuthError as exc:
        return jsonify({"error": exc.code, "message": exc.message}), exc.status_code
