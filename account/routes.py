# account/routes.py
from __future__ import annotations

from flask import render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from db_transaction_manager import get_db_session
from models import Session, User
from utils.timezone_choices import (
    TIMEZONE_CHOICES,
    TIMEZONE_VALUES,
    DEFAULT_TIMEZONE,
    TIMEZONE_LABELS,
)

from auth.security import (
    check_password_strength,
    validate_email,
    validate_phone,
    hash_password,
    verify_password,
)
from . import account_bp


@account_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    """
    Let the logged-in user edit their own profile fields.
    (We keep HR fields like year_of_joining / last_date_of_service admin-only.)
    """
    if request.method == "POST":
        full_name   = (request.form.get("full_name") or "").strip()
        designation = (request.form.get("designation") or "").strip()
        email       = (request.form.get("email") or "").strip()
        phone       = (request.form.get("phone") or "").strip()
        timezone_pref = (request.form.get("timezone") or "").strip()

        ok, msg = validate_email(email)
        if not ok:
            flash(msg, "danger")
            # include roles on error
            with get_db_session() as db:
                roles = db.execute(
                    select(User).options(selectinload(User.roles)).where(User.id == current_user.id)
                ).scalar_one().roles or []
            default_tz = current_app.config.get("DEFAULT_DISPLAY_TIMEZONE", DEFAULT_TIMEZONE)
            # Render template within the same session to avoid detached instance errors
            return render_template("account/profile.html",
                                   full_name=full_name, designation=designation, email=email, phone=phone,
                                   timezone=timezone_pref,
                                   timezone_choices=TIMEZONE_CHOICES,
                                   timezone_labels=TIMEZONE_LABELS,
                                   selected_timezone=timezone_pref or default_tz,
                                   default_timezone=default_tz,
                                   roles=[r.name for r in roles])

        ok, msg = validate_phone(phone)
        if not ok:
            flash(msg, "danger")
            with get_db_session() as db:
                roles = db.execute(
                    select(User).options(selectinload(User.roles)).where(User.id == current_user.id)
                ).scalar_one().roles or []
            default_tz = current_app.config.get("DEFAULT_DISPLAY_TIMEZONE", DEFAULT_TIMEZONE)
            # Render template within the same session to avoid detached instance errors
            return render_template("account/profile.html",
                                   full_name=full_name, designation=designation, email=email, phone=phone,
                                   timezone=timezone_pref,
                                   timezone_choices=TIMEZONE_CHOICES,
                                   timezone_labels=TIMEZONE_LABELS,
                                   selected_timezone=timezone_pref or default_tz,
                                   default_timezone=default_tz,
                                   roles=[r.name for r in roles])

        if timezone_pref and timezone_pref not in TIMEZONE_VALUES:
            flash("Please select a valid timezone.", "danger")
            with get_db_session() as db:
                roles = db.execute(
                    select(User).options(selectinload(User.roles)).where(User.id == current_user.id)
                ).scalar_one().roles or []
            default_tz = current_app.config.get("DEFAULT_DISPLAY_TIMEZONE", DEFAULT_TIMEZONE)
            # Render template within the same session to avoid detached instance errors
            return render_template("account/profile.html",
                                   full_name=full_name, designation=designation, email=email, phone=phone,
                                   timezone=timezone_pref,
                                   timezone_choices=TIMEZONE_CHOICES,
                                   timezone_labels=TIMEZONE_LABELS,
                                   selected_timezone=timezone_pref or default_tz,
                                   default_timezone=default_tz,
                                   roles=[r.name for r in roles])

        stored_timezone = None
        with get_db_session() as db:
            # Reload your user to update
            user = db.get(User, current_user.id)
            if not user:
                flash("User not found.", "danger")
                return redirect(url_for("homepage"))

            user.full_name  = full_name or None
            user.designation = designation or None
            user.email      = email or None
            user.phone      = phone or None
            default_tz = current_app.config.get("DEFAULT_DISPLAY_TIMEZONE", DEFAULT_TIMEZONE)
            user.timezone  = timezone_pref or default_tz
            stored_timezone = user.timezone

            db.add(user)

        # Ensure the session knows about the updated preference immediately
        try:
            current_user.timezone = stored_timezone
        except Exception:
            pass

        flash("Profile updated.", "success")
        return redirect(url_for("account.profile"))

    # GET — prefill with current data + roles
    with get_db_session() as db:
        user = db.execute(
            select(User).options(selectinload(User.roles)).where(User.id == current_user.id)
        ).scalar_one()
        roles = [r.name for r in (user.roles or [])]
        default_tz = current_app.config.get("DEFAULT_DISPLAY_TIMEZONE", DEFAULT_TIMEZONE)
        
        # Access user.timezone while still in session context to avoid detached instance errors
        selected_timezone = user.timezone or default_tz
        
        # Render template within the same session to avoid detached instance errors
        return render_template(
            "account/profile.html",
            roles=roles,
            timezone_choices=TIMEZONE_CHOICES,
            timezone_labels=TIMEZONE_LABELS,
            selected_timezone=selected_timezone,
            default_timezone=default_tz,
        )


@account_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password_self():
    """
    Let the logged-in user change their own password.
    Requires current password; enforces strength policy.
    """
    if request.method == "POST":
        current_pw = request.form.get("current_password") or ""
        new_pw     = request.form.get("new_password") or ""
        confirm_pw = request.form.get("confirm_password") or ""

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

            ok, msg = check_password_strength(new_pw, min_len=10)
            if not ok:
                flash(msg, "danger")
                return render_template("account/change_password.html")

            if new_pw != confirm_pw:
                flash("Passwords do not match.", "danger")
                return render_template("account/change_password.html")

            # Set new password + clear any lock
            user.password_hash = hash_password(new_pw)
            user.is_locked_until = None
            db.add(user)

        try:
            current_app.logger.info("User '%s' changed their password", getattr(current_user, "username", "unknown"))
        except Exception:
            pass

        flash("Password changed.", "success")
        return redirect(url_for("account.change_password_self"))

    # GET
    return render_template("account/change_password.html")
