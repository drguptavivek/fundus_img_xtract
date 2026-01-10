# account/routes.py
from __future__ import annotations

from flask import render_template, request, redirect, url_for, flash, current_app, session
from flask_login import login_required, current_user
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from db_transaction_manager import get_db_session
from models import User
from utils.timezone_choices import (
    TIMEZONE_CHOICES,
    TIMEZONE_VALUES,
    DEFAULT_TIMEZONE,
    TIMEZONE_LABELS,
)

from auth.security import (
    validate_email,
    validate_phone,
    hash_password,
    verify_password,
    generate_strong_password,
)
from utils.emails import send_email_sync
from utils.rate_limiter import rate_limit
from . import account_bp

PROFILE_TEMPLATE = "account/profile.html"


def _get_profile_form_data() -> dict[str, str]:
    return {
        "full_name": (request.form.get("full_name") or "").strip(),
        "designation": (request.form.get("designation") or "").strip(),
        "email": (request.form.get("email") or "").strip(),
        "phone": (request.form.get("phone") or "").strip(),
        "timezone_pref": (request.form.get("timezone") or "").strip(),
    }


def _render_profile_form(
    full_name: str,
    designation: str,
    email: str,
    phone: str,
    timezone_pref: str,
) -> str:
    with get_db_session() as db:
        roles = db.execute(
            select(User).options(selectinload(User.roles)).where(User.id == current_user.id)
        ).scalar_one().roles or []
    default_tz = current_app.config.get("DEFAULT_DISPLAY_TIMEZONE", DEFAULT_TIMEZONE)
    return render_template(
        PROFILE_TEMPLATE,
        full_name=full_name,
        designation=designation,
        email=email,
        phone=phone,
        timezone=timezone_pref,
        timezone_choices=TIMEZONE_CHOICES,
        timezone_labels=TIMEZONE_LABELS,
        selected_timezone=timezone_pref or default_tz,
        default_timezone=default_tz,
        roles=[r.name for r in roles],
    )


def _validate_profile_inputs(email: str, phone: str, timezone_pref: str) -> str | None:
    ok, msg = validate_email(email)
    if not ok:
        return msg

    ok, msg = validate_phone(phone)
    if not ok:
        return msg

    if timezone_pref and timezone_pref not in TIMEZONE_VALUES:
        return "Please select a valid timezone."

    return None


def _update_profile(data: dict[str, str]) -> tuple[bool, str | None]:
    stored_timezone = None
    with get_db_session() as db:
        user = db.get(User, current_user.id)
        if not user:
            return False, "User not found."

        user.full_name = data["full_name"] or None
        user.designation = data["designation"] or None
        user.email = data["email"] or None
        user.phone = data["phone"] or None
        default_tz = current_app.config.get("DEFAULT_DISPLAY_TIMEZONE", DEFAULT_TIMEZONE)
        user.timezone = data["timezone_pref"] or default_tz
        stored_timezone = user.timezone

        db.add(user)

    try:
        current_user.timezone = stored_timezone
    except Exception:
        pass

    return True, None


def _render_profile_get() -> str:
    with get_db_session() as db:
        user = db.execute(
            select(User).options(selectinload(User.roles)).where(User.id == current_user.id)
        ).scalar_one()
        roles = [r.name for r in (user.roles or [])]
        default_tz = current_app.config.get("DEFAULT_DISPLAY_TIMEZONE", DEFAULT_TIMEZONE)
        selected_timezone = user.timezone or default_tz
        return render_template(
            PROFILE_TEMPLATE,
            roles=roles,
            timezone_choices=TIMEZONE_CHOICES,
            timezone_labels=TIMEZONE_LABELS,
            selected_timezone=selected_timezone,
            default_timezone=default_tz,
        )


@account_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    """
    Let the logged-in user edit their own profile fields.
    (We keep HR fields like year_of_joining / last_date_of_service admin-only.)
    """
    if request.method == "POST":
        data = _get_profile_form_data()
        error = _validate_profile_inputs(data["email"], data["phone"], data["timezone_pref"])
        if error:
            flash(error, "danger")
            return _render_profile_form(
                full_name=data["full_name"],
                designation=data["designation"],
                email=data["email"],
                phone=data["phone"],
                timezone_pref=data["timezone_pref"],
            )

        updated, error = _update_profile(data)
        if not updated:
            flash(error or "User not found.", "danger")
            return redirect(url_for("homepage"))

        flash("Profile updated.", "success")
        return redirect(url_for("account.profile"))

    return _render_profile_get()


@account_bp.route("/change-password", methods=["GET"])
@login_required
def change_password_self():
    """Render the change password form for the logged-in user."""
    return render_template("account/change_password.html", username=current_user.username)


@account_bp.route("/change-password/submit", methods=["POST"])
@rate_limit("10 per minute")
@login_required
def change_password_submit():
    """
    Let the logged-in user change their own password.
    Requires current password; generates a strong password automatically.
    """
    current_pw = request.form.get("current_password") or ""
    new_pw = generate_strong_password(12)

    # Verify current password
    with get_db_session() as db:
        user = db.get(User, current_user.id)
        if not user:
            flash("User not found.", "danger")
            return redirect(url_for("homepage"))

        if not verify_password(user.password_hash, current_pw):
            flash("Current password is incorrect.", "danger")
            # Render template within the same session to avoid detached instance errors
            return render_template("account/change_password.html")

        # Set new password + clear any lock
        user.password_hash = hash_password(new_pw)
        user.is_locked_until = None
        db.add(user)
        username = user.username
        full_name = user.full_name
        email = user.email or ""

    try:
        current_app.logger.info("User '%s' changed their password", getattr(current_user, "username", "unknown"))
    except Exception:
        pass

    email_sent = None
    if email:
        subject = "Your Eye Image Manager password"
        login_url = url_for("auth.login", _external=True)
        display_name = full_name or username
        body = f"""
Hello {display_name},

Your Eye Image Manager password has been reset.

Username: {username}
Password: {new_pw}
Login: {login_url}

Please keep this information secure.
"""
        email_sent = send_email_sync(email, subject, body)

    session["password_change_info"] = {
        "username": username,
        "password": new_pw,
        "email": email,
        "email_sent": bool(email_sent) if email else None,
    }
    return redirect(url_for("account.password_changed"))


@account_bp.route("/password-changed", methods=["GET"])
@login_required
def password_changed():
    info = session.pop("password_change_info", None)
    if not info:
        flash("No recent password change details found.", "warning")
        return redirect(url_for("account.change_password_self"))

    if info.get("email"):
        if info.get("email_sent") is True:
            flash(f"Password details sent to {info['email']}.", "info")
        elif info.get("email_sent") is False:
            flash(f"Failed to send password details to {info['email']}.", "warning")
    else:
        flash("No email address on file. Please share the password securely.", "warning")

    return render_template("account/password_changed.html", info=info)
