"""Session APIs for requesting, confirming, approving and revoking project data sync grants.

The desktop client itself uses the credential-authenticated surface in
``api/sync``; these endpoints manage the grant lifecycle from the web app.
See docs/API/project_sync/README.md.
"""
from __future__ import annotations

import time

from flask import jsonify, request, session, url_for
from flask_login import current_user, login_required

from auth.roles import roles_required
from auth.utils import get_client_ip
from db_transaction_manager import transaction_scope
from project_sync import notifications
from project_sync.dto import RequestMeta, SyncGrantRequest
from project_sync.exceptions import ProjectSyncError, ProjectSyncValidationError
from project_sync.service import (
    admin_recipients,
    approve_grant,
    confirm_email,
    eligible_projects,
    issue_credential,
    list_admin_grants,
    list_user_grants,
    reject_grant,
    request_grant,
    revoke_grant,
    sync_enabled,
)
from utils.rate_limiter import rate_limit

from . import api_bp

REAUTH_SECONDS = 600


def _meta() -> RequestMeta:
    return RequestMeta(ip_address=get_client_ip(), user_agent=request.headers.get("User-Agent", ""))


def _error(exc: ProjectSyncError):
    return jsonify({"error": exc.code, "message": exc.message}), exc.status_code


def _reauth_response():
    """JSON step-up: the caller must re-enter their password first."""
    last_sudo = session.get("last_sudo_time")
    if last_sudo and int(time.time()) - int(last_sudo) <= REAUTH_SECONDS:
        return None
    next_url = request.headers.get("HX-Current-URL") or url_for("project_sync_pages.index")
    return jsonify(
        {
            "error": "reauth_required",
            "message": "Confirm your password to continue.",
            "reauth_url": url_for("auth.confirm_password", next=next_url),
        }
    ), 401


def _payload() -> dict:
    payload = request.get_json(silent=True)
    if payload is None:
        payload = request.form.to_dict()
    if not isinstance(payload, dict):
        raise ProjectSyncValidationError("Request body must be a JSON object.")
    return payload


def _bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _positive_int(value, name: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ProjectSyncValidationError(f"{name} must be a positive integer.") from None
    if number < 1:
        raise ProjectSyncValidationError(f"{name} must be a positive integer.")
    return number


@api_bp.route("/project-sync/status", methods=["GET"])
@login_required
def project_sync_status():
    with transaction_scope() as db:
        return jsonify(
            {
                "enabled": sync_enabled(),
                "eligible_projects": eligible_projects(db, current_user) if sync_enabled() else [],
                "grants": [grant.to_dict() for grant in list_user_grants(db, user=current_user)],
            }
        )


@api_bp.route("/project-sync/grants", methods=["POST"])
@login_required
@rate_limit("10 per hour")
def project_sync_request_grant():
    reauth = _reauth_response()
    if reauth:
        return reauth
    try:
        payload = _payload()
        grant_request = SyncGrantRequest(
            project_id=_positive_int(payload.get("project_id"), "project_id"),
            purpose=str(payload.get("purpose") or ""),
            include_pii=_bool(payload.get("include_pii")),
        )
        with transaction_scope() as db:
            result = request_grant(db, user=current_user, request=grant_request, meta=_meta())
    except ProjectSyncError as exc:
        return _error(exc)
    notifications.send_confirmation_email(result)
    return jsonify({"grant": result.grant.to_dict(), "email_sent_to": notifications.masked(result.recipient_email)}), 201


@api_bp.route("/project-sync/grants/confirm-email", methods=["POST"])
@login_required
@rate_limit("20 per hour")
def project_sync_confirm_email():
    try:
        payload = _payload()
        with transaction_scope() as db:
            grant = confirm_email(db, user=current_user, token=str(payload.get("token") or ""), meta=_meta())
            admins = admin_recipients(db)
    except ProjectSyncError as exc:
        return _error(exc)
    notifications.notify_admins_pending(grant, admins)
    return jsonify({"grant": grant.to_dict()})


@api_bp.route("/project-sync/grants/<int:grant_id>/credential", methods=["POST"])
@login_required
@rate_limit("10 per hour")
def project_sync_issue_credential(grant_id: int):
    reauth = _reauth_response()
    if reauth:
        return reauth
    try:
        with transaction_scope() as db:
            issued = issue_credential(db, user=current_user, grant_id=grant_id, meta=_meta())
    except ProjectSyncError as exc:
        return _error(exc)
    notifications.notify_credential_issued(issued.grant, getattr(current_user, "email", None))
    response = jsonify({"grant": issued.grant.to_dict(), "credential": issued.credential})
    response.headers["Cache-Control"] = "no-store"
    return response


@api_bp.route("/project-sync/grants/<int:grant_id>/revoke", methods=["POST"])
@login_required
def project_sync_revoke(grant_id: int):
    try:
        payload = _payload()
        with transaction_scope() as db:
            grant = revoke_grant(db, actor=current_user, grant_id=grant_id,
                                 reason=str(payload.get("reason") or ""), meta=_meta())
    except ProjectSyncError as exc:
        return _error(exc)
    return jsonify({"grant": grant.to_dict()})


@api_bp.route("/project-sync/admin/grants", methods=["GET"])
@login_required
@roles_required("admin")
def project_sync_admin_list():
    status = (request.args.get("status") or "").strip() or None
    try:
        with transaction_scope() as db:
            grants = list_admin_grants(db, admin=current_user, status=status)
    except ProjectSyncError as exc:
        return _error(exc)
    return jsonify({"enabled": sync_enabled(), "grants": [grant.to_dict() for grant in grants]})


@api_bp.route("/project-sync/admin/grants/<int:grant_id>/approve", methods=["POST"])
@login_required
@roles_required("admin")
def project_sync_admin_approve(grant_id: int):
    reauth = _reauth_response()
    if reauth:
        return reauth
    try:
        payload = _payload()
        valid_days = payload.get("valid_days")
        with transaction_scope() as db:
            grant = approve_grant(
                db,
                admin=current_user,
                grant_id=grant_id,
                note=str(payload.get("note") or ""),
                valid_days=_positive_int(valid_days, "valid_days") if valid_days not in (None, "") else None,
                meta=_meta(),
            )
            requester_email = _grant_owner_email(db, grant.user_id)
    except ProjectSyncError as exc:
        return _error(exc)
    notifications.notify_requester_decision(grant, requester_email)
    return jsonify({"grant": grant.to_dict()})


@api_bp.route("/project-sync/admin/grants/<int:grant_id>/reject", methods=["POST"])
@login_required
@roles_required("admin")
def project_sync_admin_reject(grant_id: int):
    try:
        payload = _payload()
        with transaction_scope() as db:
            grant = reject_grant(db, admin=current_user, grant_id=grant_id,
                                 note=str(payload.get("note") or ""), meta=_meta())
            requester_email = _grant_owner_email(db, grant.user_id)
    except ProjectSyncError as exc:
        return _error(exc)
    notifications.notify_requester_decision(grant, requester_email)
    return jsonify({"grant": grant.to_dict()})


def _grant_owner_email(db, user_id: int) -> str | None:
    from models import User

    user = db.get(User, user_id)
    return user.email if user else None
