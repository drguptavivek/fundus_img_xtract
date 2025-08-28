# account/routes.py
from __future__ import annotations

from flask import render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from models import Session, User

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

        ok, msg = validate_email(email)
        if not ok:
            flash(msg, "danger")
            # include roles on error
            with Session() as db:
                roles = db.execute(
                    select(User).options(selectinload(User.roles)).where(User.id == current_user.id)
                ).scalar_one().roles or []
            return render_template("account/profile.html",
                                   full_name=full_name, designation=designation, email=email, phone=phone,
                                   roles=[r.name for r in roles])

        ok, msg = validate_phone(phone)
        if not ok:
            flash(msg, "danger")
            with Session() as db:
                roles = db.execute(
                    select(User).options(selectinload(User.roles)).where(User.id == current_user.id)
                ).scalar_one().roles or []
            return render_template("account/profile.html",
                                   full_name=full_name, designation=designation, email=email, phone=phone,
                                   roles=[r.name for r in roles])


        with Session() as db:
            # Reload your user to update
            user = db.get(User, current_user.id)
            if not user:
                flash("User not found.", "danger")
                return redirect(url_for("homepage"))

            user.full_name  = full_name or None
            user.designation = designation or None
            user.email      = email or None
            user.phone      = phone or None

            db.add(user); db.commit()

        flash("Profile updated.", "success")
        return redirect(url_for("account.profile"))

    # GET — prefill with current data + roles
    with Session() as db:
        user = db.execute(
            select(User).options(selectinload(User.roles)).where(User.id == current_user.id)
        ).scalar_one()
        roles = [r.name for r in (user.roles or [])]
    return render_template("account/profile.html", roles=roles)


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
        with Session() as db:
            user = db.get(User, current_user.id)
            if not user:
                flash("User not found.", "danger")
                return redirect(url_for("homepage"))

            if not verify_password(user.password_hash, current_pw):
                flash("Current password is incorrect.", "danger")
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
            db.add(user); db.commit()

        try:
            current_app.logger.info("User '%s' changed their password", getattr(current_user, "username", "unknown"))
        except Exception:
            pass

        flash("Password changed.", "success")
        return redirect(url_for("account.change_password_self"))

    # GET
    return render_template("account/change_password.html")
