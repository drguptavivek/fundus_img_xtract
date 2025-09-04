import re
from flask import render_template, request, redirect, url_for, flash, current_app
from sqlalchemy import select, func
from flask_login import current_user
from auth.roles import roles_required
from auth.security import hash_password, check_password_strength
from models import User, Role, Session


def change_password():
    """
    Admin can change any user's password by username (case-insensitive).
    Lockout is cleared after reset.
    """
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        new_pw = request.form.get("new_password") or ""
        confirm_pw = request.form.get("confirm_password") or ""

        # Basic validation
        if not username:
            flash("Username is required.", "danger")
            return render_template("admin/change_password.html", username=username)

        if len(new_pw) < 10:
            flash("Password should be at least 10 characters.", "danger")
            return render_template("admin/change_password.html", username=username)
        
        ok, msg = check_password_strength(new_pw, min_len=10)
        if not ok:
            flash(msg, "danger")
            return render_template("admin/change_password.html", username=username)

        if new_pw != confirm_pw:
            flash("Passwords do not match.", "danger")
            return render_template("admin/change_password.html", username=username)

        # Update in DB
        with Session() as db:
            user = db.execute(
                select(User).where(func.lower(User.username) == username.lower())
            ).scalar_one_or_none()

            if not user:
                flash("User not found.", "danger")
                return render_template("admin/change_password.html", username=username)

            user.password_hash = hash_password(new_pw)
            user.is_locked_until = None  # optional: clear any lockouts
            db.add(user)
            db.commit()

        # Audit (no secrets)
        try:
            current_app.logger.info(
                "Admin '%s' changed password for user '%s'",
                getattr(current_user, "username", "unknown"),
                username,
            )
        except Exception:
            pass

        flash(f"Password updated for '{username}'.", "success")
        return redirect(url_for("admin.change_password"))

    # GET
    return render_template("admin/change_password.html")


def manage_roles():
    """
    Show all roles and allow admins to add a new role.
    - Names are lowercase, 2–32 chars, start with a letter, then letters/digits/_.
    - Duplicate names (case-insensitive) are rejected.
    """
    if request.method == "POST":
        name_raw = (request.form.get("name") or "").strip()
        name = name_raw.lower()

        # Validate name
        if not re.fullmatch(r"[a-z][a-z0-9_]{1,31}", name):
            flash("Role name must be 2–32 chars, lowercase, start with a letter, and contain only letters, digits, or _.", "danger")
            # fall through to re-render list below
        else:
            with Session() as db:
                exists = db.execute(
                    select(Role).where(func.lower(Role.name) == name)
                ).scalar_one_or_none()
                if exists:
                    flash(f"Role '{name}' already exists.", "warning")
                else:
                    db.add(Role(name=name))
                    db.commit()
                    flash(f"Role '{name}' added.", "success")
                    return redirect(url_for("admin.manage_roles"))

    # GET (or POST with validation errors): show current roles
    with Session() as db:
        roles = db.execute(select(Role).order_by(Role.name.asc())).scalars().all()

    return render_template("admin/roles.html", roles=roles)