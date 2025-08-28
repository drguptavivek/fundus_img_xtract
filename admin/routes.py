# admin/routes.py
from __future__ import annotations
from datetime import datetime, date, timezone
import re
from sqlite3 import IntegrityError

from flask import render_template, request, redirect, url_for, flash, current_app
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from flask_login import current_user
from auth.roles import roles_required
from auth.security import hash_password
from models import Role, Session, User  # ← uses your session factory & model

from auth.security import (
    hash_password, check_password_strength, validate_username,
    validate_email, validate_phone, parse_iso_date
)


from . import admin_bp


@admin_bp.get("/users")
@roles_required("admin")
def users_list():
    """List all users with roles and active status."""
    with Session() as db:
        users = db.execute(
            select(User)
            .options(selectinload(User.roles))
            .order_by(User.username.asc())
        ).scalars().all()

        roles = db.execute(
            select(Role).order_by(Role.name.asc())
        ).scalars().all()

    return render_template("admin/users.html", users=users, roles=roles)


@admin_bp.route("/users/new", methods=["GET", "POST"])
@roles_required("admin")
def add_user():
    pre_username = (request.form.get("username") or request.args.get("username") or "").strip()
    pre_active = bool(request.form.get("active")) if request.method == "POST" else True
    pre_roles = set(request.form.getlist("roles")) if request.method == "POST" else set()

    # profile prefill
    pre_full_name = (request.form.get("full_name") or "").strip()
    pre_phone = (request.form.get("phone") or "").strip()
    pre_designation = (request.form.get("designation") or "").strip()
    pre_email = (request.form.get("email") or "").strip()
    pre_yj = (request.form.get("year_of_joining") or "").strip()
    pre_ldos = (request.form.get("last_date_of_service") or "").strip()

    with Session() as db:
        roles = db.execute(select(Role).order_by(Role.name.asc())).scalars().all()

    if request.method == "POST":
        username = pre_username
        password = request.form.get("new_password") or ""
        confirm = request.form.get("confirm_password") or ""

        ok, msg = validate_username(username);           0
        if not ok: return _add_user_err(msg, roles, username, pre_active, pre_roles,
                                        pre_full_name, pre_phone, pre_designation, pre_email, pre_yj, pre_ldos)

        ok, msg = check_password_strength(password, min_len=10)
        if not ok: return _add_user_err(msg, roles, username, pre_active, pre_roles,
                                        pre_full_name, pre_phone, pre_designation, pre_email, pre_yj, pre_ldos)

        if password != confirm:
            return _add_user_err("Passwords do not match.", roles, username, pre_active, pre_roles,
                                 pre_full_name, pre_phone, pre_designation, pre_email, pre_yj, pre_ldos)

        ok, msg = validate_email(pre_email)
        if not ok: return _add_user_err(msg, roles, username, pre_active, pre_roles,
                                        pre_full_name, pre_phone, pre_designation, pre_email, pre_yj, pre_ldos)

        ok, msg = validate_phone(pre_phone)
        if not ok: return _add_user_err(msg, roles, username, pre_active, pre_roles,
                                        pre_full_name, pre_phone, pre_designation, pre_email, pre_yj, pre_ldos)

        yj_int = None
        if pre_yj:
            current_year = date.today().year
            if not pre_yj.isdigit() or not (1970 <= int(pre_yj) <= current_year + 1):
                return _add_user_err("Year of joining must be a valid year.", roles, username, pre_active, pre_roles,
                                      pre_full_name, pre_phone, pre_designation, pre_email, pre_yj, pre_ldos)
            yj_int = int(pre_yj)

        ok, msg, ldos_date = parse_iso_date(pre_ldos)
        if not ok:
            return _add_user_err(msg, roles, username, pre_active, pre_roles,
                                 pre_full_name, pre_phone, pre_designation, pre_email, pre_yj, pre_ldos)

        with Session() as db:
            exists = db.execute(
                select(User).where(func.lower(User.username) == username.lower())
            ).scalar_one_or_none()
            if exists:
                return _add_user_err("Username already exists.", roles, username, pre_active, pre_roles,
                                     pre_full_name, pre_phone, pre_designation, pre_email, pre_yj, pre_ldos)

            user = User(
                username=username,
                password_hash=hash_password(password),
                is_active=pre_active,
                is_locked_until=None,
                full_name=pre_full_name or None,
                phone=pre_phone or None,
                designation=pre_designation or None,
                email=pre_email or None,
                year_of_joining=yj_int,
                last_date_of_service=ldos_date,
            )

            if pre_roles:
                role_objs = db.execute(select(Role).where(Role.name.in_(pre_roles))).scalars().all()
                for r in role_objs: user.roles.append(r)

            db.add(user); db.commit()

        flash(f"User '{username}' created.", "success")
        return redirect(url_for("admin.users_list"))

    return render_template("admin/add_user.html",
                           roles=roles, username=pre_username, active=pre_active, selected_roles=pre_roles,
                           full_name=pre_full_name, phone=pre_phone, designation=pre_designation, email=pre_email,
                           year_of_joining=pre_yj, last_date_of_service=pre_ldos)

def _add_user_err(msg, roles, username, active, selected_roles, full_name, phone, designation, email, yj, ldos):
    flash(msg, "danger")
    return render_template("admin/add_user.html",
                           roles=roles, username=username, active=active, selected_roles=selected_roles,
                           full_name=full_name, phone=phone, designation=designation, email=email,
                           year_of_joining=yj, last_date_of_service=ldos)



@admin_bp.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
@roles_required("admin")
def edit_user(user_id: int):
    with Session() as db:
        user = db.get(User, user_id)
        if not user:
            flash("User not found.", "danger"); return redirect(url_for("admin.users_list"))

        if request.method == "POST":
            full_name = (request.form.get("full_name") or "").strip()
            designation = (request.form.get("designation") or "").strip()
            email = (request.form.get("email") or "").strip()
            phone = (request.form.get("phone") or "").strip()
            yj = (request.form.get("year_of_joining") or "").strip()
            ldos = (request.form.get("last_date_of_service") or "").strip()

            ok, msg = validate_email(email)
            if not ok: flash(msg, "danger"); return render_template("admin/edit_user.html", user=user)

            ok, msg = validate_phone(phone)
            if not ok: flash(msg, "danger"); return render_template("admin/edit_user.html", user=user)

            yj_int = None
            if yj:
               current_year = date.today().year
               if not yj.isdigit() or not (1970 <= int(yj) <= current_year + 1):
                     flash("Year of joining must be a valid year.", "danger")
                     return render_template("admin/edit_user.html", user=user)
               yj_int = int(yj)

            ok, msg, ldos_date = parse_iso_date(ldos)
            if not ok: flash(msg, "danger"); return render_template("admin/edit_user.html", user=user)

            user.full_name = full_name or None
            user.designation = designation or None
            user.email = email or None
            user.phone = phone or None
            user.year_of_joining = yj_int
            user.last_date_of_service = ldos_date

            db.add(user); db.commit()
            flash("Profile updated.", "success")
            return redirect(url_for("admin.users_list"))

        # GET
        return render_template("admin/edit_user.html", user=user)


# ROUTE FOR ROLES AND TO MAKE ACTIVE/INACTIVE
@admin_bp.post("/users/<int:user_id>/update")
@roles_required("admin")
def users_update(user_id: int):
    """
    Update a user's active flag and roles from the users list.
    Prevents self-deactivation and prevents removing/deactivating the last active admin.
    """
    selected_roles = set(request.form.getlist("roles"))       # role names
    new_active = bool(request.form.get("active"))             # checkbox present -> True

    with Session() as db:
        user = db.get(User, user_id)
        if not user:
            flash("User not found.", "danger")
            return redirect(url_for("admin.users_list"))

        # 1) Don't let an admin deactivate themselves
        if user.id == getattr(current_user, "id", None) and not new_active:
            flash("You cannot deactivate your own account.", "warning")
            return redirect(url_for("admin.users_list"))

        # Normalize role names to ones that exist in DB (ignore stray/unknown values)
        valid_role_names = set(db.execute(select(Role.name)).scalars().all())
        selected_roles &= valid_role_names

        existing = {r.name for r in (user.roles or [])}
        will_remove = existing - selected_roles
        will_add = selected_roles - existing

        # 2) Ensure at least one ACTIVE admin remains after this change
        active_admins = db.execute(
            select(func.count(User.id))
            .join(User.roles)
            .where(Role.name == "admin", User.is_active.is_(True))
        ).scalar_one() or 0

        is_admin_before = ("admin" in existing) and bool(user.is_active)
        is_admin_after  = ("admin" in selected_roles) and bool(new_active)

        if is_admin_before and not is_admin_after:
            # This change would remove/deactivate an active admin account.
            if active_admins <= 1:
                flash("There must be at least one active admin user.", "warning")
                return redirect(url_for("admin.users_list"))

        # 3) Apply changes
        user.is_active = new_active

        # remove roles
        if user.roles:
            user.roles[:] = [r for r in user.roles if r.name not in will_remove]

        # add roles
        if will_add:
            add_objs = db.execute(select(Role).where(Role.name.in_(will_add))).scalars().all()
            for r in add_objs:
                user.roles.append(r)

        db.add(user)
        db.commit()

        try:
            current_app.logger.info(
                "Admin '%s' updated user '%s': active=%s, roles=%s",
                getattr(current_user, "username", "unknown"),
                user.username,
                user.is_active,
                [r.name for r in (user.roles or [])],
            )
        except Exception:
            pass

    flash("User updated.", "success")
    return redirect(url_for("admin.users_list"))






@admin_bp.route("/change-password", methods=["GET", "POST"])
@roles_required("admin")  # admin-only
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



@admin_bp.route("/roles", methods=["GET", "POST"])
@roles_required("admin")
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