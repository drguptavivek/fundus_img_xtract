"""REST API for system-admin user impersonation."""

from flask import abort, current_app, jsonify, request, session
from flask_login import current_user, login_required, login_user, logout_user

from auth.impersonation import ImpersonationError, start_impersonation, stop_impersonation
from db_transaction_manager import transaction_scope

from . import api_bp


ORIGINAL_USER_ID_KEY = "impersonation_original_user_id"
ORIGINAL_USERNAME_KEY = "impersonation_original_username"


def _client_context() -> tuple[str | None, str | None]:
    return request.remote_addr, request.user_agent.string or None


def _regenerate_session_id() -> None:
    regenerate = getattr(current_app.session_interface, "regenerate", None)
    if callable(regenerate):
        regenerate(session)


@api_bp.before_app_request
def enforce_read_only_impersonation():
    """Prevent an impersonated identity from changing clinical or account state."""
    if ORIGINAL_USER_ID_KEY not in session or request.method in {"GET", "HEAD", "OPTIONS"}:
        return None
    if request.endpoint in {"fundus_api.api_stop_impersonation", "auth.logout"}:
        return None
    if request.path.startswith("/api/") or request.is_json:
        return jsonify({
            "success": False,
            "error": "Impersonation is read-only. Return to the admin account to make changes.",
        }), 403
    abort(403, description="Impersonation is read-only. Return to the admin account to make changes.")


@api_bp.post("/admin/impersonation")
@login_required
def api_start_impersonation():
    payload = request.get_json(silent=True) or {}
    try:
        target_user_id = int(payload.get("user_id"))
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "user_id must be an integer."}), 400

    ip_address, user_agent = _client_context()
    try:
        with transaction_scope() as db:
            result = start_impersonation(
                db,
                actor_user_id=current_user.id,
                target_user_id=target_user_id,
                already_impersonating=ORIGINAL_USER_ID_KEY in session,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            original_id = result.original_user.id
            original_username = result.original_user.username
            target_id = result.effective_user.id
            target_username = result.effective_user.username
    except ImpersonationError as exc:
        return jsonify({"success": False, "error": str(exc)}), exc.status_code

    session[ORIGINAL_USER_ID_KEY] = original_id
    session[ORIGINAL_USERNAME_KEY] = original_username
    from auth.routes import load_user
    target = load_user(str(target_id))
    if target is None:
        session.pop(ORIGINAL_USER_ID_KEY, None)
        session.pop(ORIGINAL_USERNAME_KEY, None)
        return jsonify({"success": False, "error": "The target user is no longer active."}), 409
    login_user(target, remember=False, fresh=False)
    _regenerate_session_id()
    session.permanent = True
    return jsonify({
        "success": True,
        "data": {
            "effective_user": {"id": target_id, "username": target_username},
            "redirect_url": "/",
        },
    })


@api_bp.delete("/admin/impersonation")
@login_required
def api_stop_impersonation():
    original_user_id = session.get(ORIGINAL_USER_ID_KEY)
    if original_user_id is None:
        return jsonify({"success": False, "error": "No impersonation session is active."}), 409

    ip_address, user_agent = _client_context()
    try:
        with transaction_scope() as db:
            result = stop_impersonation(
                db,
                original_user_id=int(original_user_id),
                effective_user_id=current_user.id,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            original_id = result.original_user.id
    except (TypeError, ValueError):
        logout_user()
        session.pop(ORIGINAL_USER_ID_KEY, None)
        session.pop(ORIGINAL_USERNAME_KEY, None)
        return jsonify({"success": False, "error": "Invalid impersonation session."}), 403
    except ImpersonationError as exc:
        logout_user()
        session.pop(ORIGINAL_USER_ID_KEY, None)
        session.pop(ORIGINAL_USERNAME_KEY, None)
        return jsonify({"success": False, "error": str(exc), "redirect_url": "/login"}), exc.status_code

    from auth.routes import load_user
    original = load_user(str(original_id))
    if original is None:
        logout_user()
        session.clear()
        return jsonify({"success": False, "error": "The original administrator account is no longer active.", "redirect_url": "/login"}), 403
    login_user(original, remember=False, fresh=False)
    _regenerate_session_id()
    session.pop(ORIGINAL_USER_ID_KEY, None)
    session.pop(ORIGINAL_USERNAME_KEY, None)
    return jsonify({"success": True, "data": {"redirect_url": "/admin/users"}})
