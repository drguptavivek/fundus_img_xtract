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
from models import Area, Camera, Disease, Hospital, LabUnit, Role, Session, User, BASE_DIR  # ← uses your session factory & model
import os
from pathlib import Path
import re as _re

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
    pre_file_upload_quota = int(request.form.get("file_upload_quota") or 0) if request.method == "POST" else 0
    pre_lab_unit_ids = set(int(x) for x in request.form.getlist("lab_units")) if request.method == "POST" else set()

    with Session() as db:
        roles = db.execute(select(Role).order_by(Role.name.asc())).scalars().all()
        hospitals = db.execute(select(Hospital).order_by(Hospital.name.asc())).scalars().all()
        lab_units = db.execute(select(LabUnit).options(selectinload(LabUnit.hospital)).order_by(LabUnit.name.asc())).scalars().all()

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
            return _add_user_err(msg, roles, hospitals, lab_units, username, pre_active, pre_roles,
                                 pre_full_name, pre_phone, pre_designation, pre_email, pre_yj, pre_ldos,
                                 pre_file_upload_quota, pre_lab_unit_ids)

        if pre_file_upload_quota < 0:
            return _add_user_err("File upload quota cannot be negative.", roles, hospitals, lab_units, username, pre_active, pre_roles,
                                 pre_full_name, pre_phone, pre_designation, pre_email, pre_yj, pre_ldos,
                                 pre_file_upload_quota, pre_lab_unit_ids)

        with Session() as db:
            exists = db.execute(
                select(User).where(func.lower(User.username) == username.lower())
            ).scalar_one_or_none()
            if exists:
                return _add_user_err("Username already exists.", roles, hospitals, lab_units, username, pre_active, pre_roles,
                                     pre_full_name, pre_phone, pre_designation, pre_email, pre_yj, pre_ldos,
                                     pre_file_upload_quota, pre_lab_unit_ids)

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
                file_upload_quota=pre_file_upload_quota,
            )

            if pre_roles:
                role_objs = db.execute(select(Role).where(Role.name.in_(pre_roles))).scalars().all()
                for r in role_objs: user.roles.append(r)

            if pre_lab_unit_ids:
                lab_unit_objs = db.execute(select(LabUnit).where(LabUnit.id.in_(pre_lab_unit_ids))).scalars().all()
                for lu in lab_unit_objs: user.lab_units.append(lu)

            db.add(user); db.commit()

        flash(f"User '{username}' created.", "success")
        return redirect(url_for("admin.users_list"))

    return render_template("admin/add_user.html",
                           roles=roles, hospitals=hospitals, lab_units=lab_units,
                           username=pre_username, active=pre_active, selected_roles=pre_roles,
                           full_name=pre_full_name, phone=pre_phone, designation=pre_designation, email=pre_email,
                           year_of_joining=pre_yj, last_date_of_service=pre_ldos,
                           file_upload_quota=pre_file_upload_quota, selected_lab_units=pre_lab_unit_ids)

def _add_user_err(msg, roles, hospitals, lab_units, username, active, selected_roles, full_name, phone, designation, email, yj, ldos, file_upload_quota, selected_lab_units):
    flash(msg, "danger")
    return render_template("admin/add_user.html",
                           roles=roles, hospitals=hospitals, lab_units=lab_units,
                           username=username, active=active, selected_roles=selected_roles,
                           full_name=full_name, phone=phone, designation=designation, email=email,
                           year_of_joining=yj, last_date_of_service=ldos,
                           file_upload_quota=file_upload_quota, selected_lab_units=selected_lab_units)



@admin_bp.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
@roles_required("admin")
def edit_user(user_id: int):
    with Session() as db:
        user = db.get(User, user_id)
        if not user:
            flash("User not found.", "danger"); return redirect(url_for("admin.users_list"))

        hospitals = db.execute(select(Hospital).order_by(Hospital.name.asc())).scalars().all()
        lab_units = db.execute(select(LabUnit).options(selectinload(LabUnit.hospital)).order_by(LabUnit.name.asc())).scalars().all()

        if request.method == "POST":
            full_name = (request.form.get("full_name") or "").strip()
            designation = (request.form.get("designation") or "").strip()
            email = (request.form.get("email") or "").strip()
            phone = (request.form.get("phone") or "").strip()
            yj = (request.form.get("year_of_joining") or "").strip()
            ldos = (request.form.get("last_date_of_service") or "").strip()
            file_upload_quota = int(request.form.get("file_upload_quota") or 0)
            selected_lab_unit_ids = set(int(x) for x in request.form.getlist("lab_units"))

            ok, msg = validate_email(email)
            if not ok: flash(msg, "danger"); return render_template("admin/edit_user.html", user=user, hospitals=hospitals, lab_units=lab_units, selected_lab_units={lu.id for lu in user.lab_units})

            ok, msg = validate_phone(phone)
            if not ok: flash(msg, "danger"); return render_template("admin/edit_user.html", user=user, hospitals=hospitals, lab_units=lab_units, selected_lab_units={lu.id for lu in user.lab_units})

            yj_int = None
            if yj:
               current_year = date.today().year
               if not yj.isdigit() or not (1970 <= int(yj) <= current_year + 1):
                     flash("Year of joining must be a valid year.", "danger")
                     return render_template("admin/edit_user.html", user=user, hospitals=hospitals, lab_units=lab_units, selected_lab_units={lu.id for lu in user.lab_units})
               yj_int = int(yj)

            ok, msg, ldos_date = parse_iso_date(ldos)
            if not ok: flash(msg, "danger"); return render_template("admin/edit_user.html", user=user, hospitals=hospitals, lab_units=lab_units, selected_lab_units={lu.id for lu in user.lab_units})

            if file_upload_quota < 0:
                flash("File upload quota cannot be negative.", "danger")
                return render_template("admin/edit_user.html", user=user, hospitals=hospitals, lab_units=lab_units, selected_lab_units={lu.id for lu in user.lab_units})

            user.full_name = full_name or None
            user.designation = designation or None
            user.email = email or None
            user.phone = phone or None
            user.year_of_joining = yj_int
            user.last_date_of_service = ldos_date
            user.file_upload_quota = file_upload_quota

            # Update lab units
            user.lab_units.clear()
            if selected_lab_unit_ids:
                lab_unit_objs = db.execute(select(LabUnit).where(LabUnit.id.in_(selected_lab_unit_ids))).scalars().all()
                for lu in lab_unit_objs: user.lab_units.append(lu)

            db.add(user); db.commit()
            flash("Profile updated.", "success")
            return redirect(url_for("admin.users_list"))

        # GET
        return render_template("admin/edit_user.html", user=user, hospitals=hospitals, lab_units=lab_units, selected_lab_units={lu.id for lu in user.lab_units})


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


@admin_bp.get("/malicious-uploads")
@roles_required("admin")
def malicious_uploads():
    """Show recent malicious upload incidents parsed from the log file with KPIs."""
    from collections import Counter
    log_path = BASE_DIR / os.getenv("MALICIOUS_UPLOAD_LOG", "logs/malicious_uploads.log")
    incidents: list[dict] = []
    try:
        if log_path.exists():
            lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
            # Keep and parse the last 1000 entries (reverse for newest-first later)
            for line in lines[-1000:]:
                # Format: [ts] zip=... user=... ip=... reason=... [expected=...] [detected=...] entry=...
                m = _re.match(r"^\[(?P<ts>[^\]]+)\]\s+(?P<rest>.*)$", line)
                if not m:
                    continue
                rest = m.group("rest")
                def kv(key: str, default: str = "-") -> str:
                    mm = _re.search(rf"\b{key}=([^\s]+)", rest)
                    return mm.group(1) if mm else default
                # entry may contain spaces; capture to end
                me = _re.search(r"\bentry=(.*)$", rest)
                incidents.append({
                    "ts": m.group("ts"),
                    "zip": kv("zip"),
                    "user": kv("user"),
                    "ip": kv("ip"),
                    "reason": kv("reason"),
                    "expected": kv("expected", ""),
                    "detected": kv("detected", ""),
                    "entry": (me.group(1).strip() if me else ""),
                })
        else:
            flash(f"Log not found: {log_path}", "warning")
    except Exception as e:
        flash(f"Failed to read log: {e}", "danger")

    # Newest first
    incidents.reverse()

    # KPIs
    total = len(incidents)
    by_user = Counter((it["user"] or "-") for it in incidents)
    by_reason = Counter((it["reason"] or "-") for it in incidents)
    by_ip = Counter((it["ip"] or "-") for it in incidents)

    # Top lists (limit 10)
    top_users = by_user.most_common(10)
    top_reasons = by_reason.most_common(10)
    top_ips = by_ip.most_common(10)

    return render_template(
        "admin/malicious_uploads.html",
        incidents=incidents,
        log_path=str(log_path),
        total=total,
        top_users=top_users,
        top_reasons=top_reasons,
        top_ips=top_ips,
    )


# --- Generic CRUD for Lookup Tables ---
def _get_model_by_name(name):
    return {
        "hospital": Hospital,
        "lab_unit": LabUnit,
        "camera": Camera,
        "disease": Disease,
        "area": Area
    }.get(name)


from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

@admin_bp.route("/<string:model_name>", methods=["GET", "POST"])
@roles_required("admin")
def list_and_create_lookup(model_name):
    Model = _get_model_by_name(model_name)
    if not Model:
        flash(f"Invalid master list: {model_name}", "danger")
        return redirect(url_for("admin.users_list"))

    # --- Handle form submission ---
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Name is required.", "danger")
            return redirect(url_for("admin.list_and_create_lookup", model_name=model_name))

        with Session() as db:
            if model_name == "lab_unit":
                hospital_id = request.form.get("hospital_id")
                if not hospital_id:
                    flash("Hospital is required for a Lab Unit.", "danger")
                    return redirect(url_for("admin.list_and_create_lookup", model_name=model_name))

                hospital_id = int(hospital_id)

                # Check for duplicate LabUnit for this hospital
                exists = db.execute(
                    select(LabUnit)
                    .where(func.lower(LabUnit.name) == name.lower())
                    .where(LabUnit.hospital_id == hospital_id)
                ).scalar_one_or_none()

                if exists:
                    flash(f"Lab Unit '{name}' already exists for this hospital.", "warning")
                else:
                    db.add(LabUnit(name=name, hospital_id=hospital_id))
                    db.commit()
                    flash(f"Lab Unit '{name}' added successfully.", "success")

            else:
                # Check for duplicate name globally
                exists = db.execute(
                    select(Model)
                    .where(func.lower(Model.name) == name.lower())
                ).scalar_one_or_none()

                if exists:
                    flash(f"{model_name.replace('_', ' ').title()} '{name}' already exists.", "warning")
                else:
                    db.add(Model(name=name))
                    db.commit()
                    flash(f"{model_name.replace('_', ' ').title()} '{name}' added successfully.", "success")

        return redirect(url_for("admin.list_and_create_lookup", model_name=model_name))

    # --- Handle listing ---
    with Session() as db:
        stmt = select(Model).order_by(Model.id)

        # Eager-load hospital relationship if model is LabUnit
        if model_name == "lab_unit":
            stmt = stmt.options(selectinload(LabUnit.hospital))

        items = db.scalars(stmt).all()
        hospitals = db.scalars(select(Hospital).order_by(Hospital.id)).all() if model_name == "lab_unit" else None

    return render_template(
        "admin/lookup_list.html",
        items=items,
        model_name=model_name,
        title=model_name.replace("_", " ").title(),
        hospitals=hospitals
    )



@admin_bp.route("/<string:model_name>/<int:item_id>/edit", methods=["GET", "POST"])
@roles_required("admin")
def edit_lookup(model_name, item_id):
    Model = _get_model_by_name(model_name)
    if not Model:
        flash(f"Invalid master list: {model_name}", "danger")
        return redirect(url_for("admin.users_list"))

    with Session() as db:
        item = db.get(Model, item_id)
        if not item:
            flash("Item not found.", "danger")
            return redirect(url_for("admin.list_and_create_lookup", model_name=model_name))

        if request.method == "POST":
            name = request.form.get("name", "").strip()
            if not name:
                flash("Name is required.", "danger")
            else:
                item.name = name
                if model_name == "lab_unit":
                    hospital_id = request.form.get("hospital_id")
                    if not hospital_id:
                        flash("Hospital is required for a Lab Unit.", "danger")
                        return redirect(url_for("admin.edit_lookup", model_name=model_name, item_id=item_id))
                    item.hospital_id = int(hospital_id)

                db.commit()
                flash(f"{model_name.replace('_', ' ').title()} updated.", "success")
                return redirect(url_for("admin.list_and_create_lookup", model_name=model_name))

        hospitals = db.scalars(select(Hospital).order_by(Hospital.name)).all() if model_name == "lab_unit" else None

    return render_template(
        "admin/lookup_edit.html",
        item=item,
        model_name=model_name,
        title=f"Edit {model_name.replace('_', ' ').title()}",
        hospitals=hospitals
    )


@admin_bp.route("/<string:model_name>/<int:item_id>/delete", methods=["POST"])
@roles_required("admin")
def delete_lookup(model_name, item_id):
    Model = _get_model_by_name(model_name)
    if not Model:
        flash(f"Invalid master list: {model_name}", "danger")
        return redirect(url_for("admin.users_list"))
    with Session() as db:
        item = db.get(Model, item_id)
        if item:
            db.delete(item)
            db.commit()
            flash(f"{model_name.replace('_', ' ').title()} deleted.", "success")
    return redirect(url_for(f"admin.list_and_create_lookup", model_name=model_name))