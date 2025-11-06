from datetime import date
from flask import render_template, request, redirect, url_for, flash, current_app
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from flask_login import current_user
from auth.roles import roles_required
from auth.security import hash_password, check_password_strength, validate_username, validate_email, validate_phone, parse_iso_date
from models import User, Role, Hospital, LabUnit
from db_transaction_manager import transaction_scope, get_db_session
from utils.timezone_choices import (
    TIMEZONE_CHOICES,
    TIMEZONE_VALUES,
    TIMEZONE_LABELS,
    DEFAULT_TIMEZONE,
)


def users_list():
    """List all users with roles, hospitals, and lab units."""
    with get_db_session() as db:
        users = db.execute(
            select(User)
            .options(selectinload(User.roles), selectinload(User.lab_units).selectinload(LabUnit.hospital))
            .order_by(User.username.asc())
        ).scalars().all()
        return render_template("admin/users.html", users=users)


def add_user():
    pre_username = (request.form.get("username") or request.args.get("username") or "").strip()
    pre_active = bool(request.form.get("active")) if request.method == "POST" else True
    pre_roles = set(request.form.getlist("roles")) if request.method == "POST" else set()
    pre_timezone = (request.form.get("timezone") or "").strip()

    # profile prefill
    pre_full_name = (request.form.get("full_name") or "").strip()
    pre_phone = (request.form.get("phone") or "").strip()
    pre_designation = (request.form.get("designation") or "").strip()
    pre_email = (request.form.get("email") or "").strip()
    pre_yj = (request.form.get("year_of_joining") or "").strip()
    pre_ldos = (request.form.get("last_date_of_service") or "").strip()
    pre_file_upload_quota = int(request.form.get("file_upload_quota") or 0) if request.method == "POST" else 0
    pre_lab_unit_ids = set(int(x) for x in request.form.getlist("lab_units")) if request.method == "POST" else set()

    with get_db_session() as db:
        roles = db.execute(select(Role).order_by(Role.name.asc())).scalars().all()
        hospitals = db.execute(select(Hospital).order_by(Hospital.name.asc())).scalars().all()
        lab_units = db.execute(select(LabUnit).options(selectinload(LabUnit.hospital)).order_by(LabUnit.name.asc())).scalars().all()

    if request.method == "POST":
        username = pre_username
        password = request.form.get("new_password") or ""
        confirm = request.form.get("confirm_password") or ""
        default_tz = current_app.config.get("DEFAULT_DISPLAY_TIMEZONE", DEFAULT_TIMEZONE)

        ok, msg = validate_username(username)
        if not ok: return _add_user_err(msg, roles, hospitals, lab_units, username, pre_active, pre_roles,
                                        pre_full_name, pre_phone, pre_designation, pre_email, pre_yj, pre_ldos,
                                        pre_file_upload_quota, pre_lab_unit_ids, pre_timezone)

        ok, msg = check_password_strength(password, min_len=10)
        if not ok: return _add_user_err(msg, roles, hospitals, lab_units, username, pre_active, pre_roles,
                                        pre_full_name, pre_phone, pre_designation, pre_email, pre_yj, pre_ldos,
                                        pre_file_upload_quota, pre_lab_unit_ids, pre_timezone)

        if password != confirm:
            return _add_user_err("Passwords do not match.", roles, hospitals, lab_units, username, pre_active, pre_roles,
                                 pre_full_name, pre_phone, pre_designation, pre_email, pre_yj, pre_ldos,
                                 pre_file_upload_quota, pre_lab_unit_ids, pre_timezone)

        ok, msg = validate_email(pre_email)
        if not ok: return _add_user_err(msg, roles, hospitals, lab_units, username, pre_active, pre_roles,
                                        pre_full_name, pre_phone, pre_designation, pre_email, pre_yj, pre_ldos,
                                        pre_file_upload_quota, pre_lab_unit_ids, pre_timezone)

        ok, msg = validate_phone(pre_phone)
        if not ok: return _add_user_err(msg, roles, hospitals, lab_units, username, pre_active, pre_roles,
                                        pre_full_name, pre_phone, pre_designation, pre_email, pre_yj, pre_ldos,
                                        pre_file_upload_quota, pre_lab_unit_ids, pre_timezone)

        if pre_timezone and pre_timezone not in TIMEZONE_VALUES:
            return _add_user_err("Please select a valid timezone.", roles, hospitals, lab_units, username, pre_active, pre_roles,
                                 pre_full_name, pre_phone, pre_designation, pre_email, pre_yj, pre_ldos,
                                 pre_file_upload_quota, pre_lab_unit_ids, pre_timezone)

        yj_int = None
        if pre_yj:
            current_year = date.today().year
            if not pre_yj.isdigit() or not (1970 <= int(pre_yj) <= current_year + 1):
                return _add_user_err("Year of joining must be a valid year.", roles, hospitals, lab_units, username, pre_active, pre_roles,
                                      pre_full_name, pre_phone, pre_designation, pre_email, pre_yj, pre_ldos,
                                      pre_file_upload_quota, pre_lab_unit_ids, pre_timezone)
            yj_int = int(pre_yj)

        ok, msg, ldos_date = parse_iso_date(pre_ldos)
        if not ok:
            return _add_user_err(msg, roles, hospitals, lab_units, username, pre_active, pre_roles,
                                 pre_full_name, pre_phone, pre_designation, pre_email, pre_yj, pre_ldos,
                                 pre_file_upload_quota, pre_lab_unit_ids, pre_timezone)

        if pre_file_upload_quota < 0:
            return _add_user_err("File upload quota cannot be negative.", roles, hospitals, lab_units, username, pre_active, pre_roles,
                                 pre_full_name, pre_phone, pre_designation, pre_email, pre_yj, pre_ldos,
                                 pre_file_upload_quota, pre_lab_unit_ids, pre_timezone)

        with transaction_scope() as db:
            exists = db.execute(
                select(User).where(func.lower(User.username) == username.lower())
            ).scalar_one_or_none()
            if exists:
                return _add_user_err("Username already exists.", roles, hospitals, lab_units, username, pre_active, pre_roles,
                                     pre_full_name, pre_phone, pre_designation, pre_email, pre_yj, pre_ldos,
                                     pre_file_upload_quota, pre_lab_unit_ids, pre_timezone)

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
                timezone=pre_timezone or default_tz,
            )

            if pre_roles:
                role_objs = db.execute(select(Role).where(Role.name.in_(pre_roles))).scalars().all()
                for r in role_objs: user.roles.append(r)

            if pre_lab_unit_ids:
                lab_unit_objs = db.execute(select(LabUnit).where(LabUnit.id.in_(pre_lab_unit_ids))).scalars().all()
                for lu in lab_unit_objs: user.lab_units.append(lu)

            db.add(user)

        flash(f"User '{username}' created.", "success")
        return redirect(url_for("admin.users_list"))

    default_tz = current_app.config.get("DEFAULT_DISPLAY_TIMEZONE", DEFAULT_TIMEZONE)
    return render_template("admin/add_user.html",
                           roles=roles, hospitals=hospitals, lab_units=lab_units,
                           username=pre_username, active=pre_active, selected_roles=pre_roles,
                           full_name=pre_full_name, phone=pre_phone, designation=pre_designation, email=pre_email,
                           year_of_joining=pre_yj, last_date_of_service=pre_ldos,
                           file_upload_quota=pre_file_upload_quota, selected_lab_units=pre_lab_unit_ids,
                           timezone_choices=TIMEZONE_CHOICES,
                           timezone_labels=TIMEZONE_LABELS,
                           selected_timezone=pre_timezone or default_tz,
                           default_timezone=default_tz)


def _add_user_err(msg, roles, hospitals, lab_units, username, active, selected_roles, full_name, phone, designation, email, yj, ldos, file_upload_quota, selected_lab_units, timezone_value):
    flash(msg, "danger")
    default_tz = current_app.config.get("DEFAULT_DISPLAY_TIMEZONE", DEFAULT_TIMEZONE)
    return render_template("admin/add_user.html",
                           roles=roles, hospitals=hospitals, lab_units=lab_units,
                           username=username, active=active, selected_roles=selected_roles,
                           full_name=full_name, phone=phone, designation=designation, email=email,
                           year_of_joining=yj, last_date_of_service=ldos,
                           file_upload_quota=file_upload_quota, selected_lab_units=selected_lab_units,
                           timezone_choices=TIMEZONE_CHOICES,
                           timezone_labels=TIMEZONE_LABELS,
                           selected_timezone=timezone_value or default_tz,
                           default_timezone=default_tz)


def edit_user(user_id: int):
    # Handle GET request (display the form)
    with get_db_session() as db:
        user = db.get(User, user_id)
        if not user:
            flash("User not found.", "danger"); return redirect(url_for("admin.users_list"))

        roles = db.execute(select(Role).order_by(Role.name.asc())).scalars().all()
        hospitals = db.execute(select(Hospital).order_by(Hospital.name.asc())).scalars().all()
        lab_units = db.execute(select(LabUnit).options(selectinload(LabUnit.hospital)).order_by(LabUnit.name.asc())).scalars().all()
        
        if request.method == "GET":
            default_tz = current_app.config.get("DEFAULT_DISPLAY_TIMEZONE", DEFAULT_TIMEZONE)
            return render_template(
                "admin/edit_user.html",
                user=user,
                roles=roles,
                hospitals=hospitals,
                lab_units=lab_units,
                selected_lab_units={lu.id for lu in user.lab_units},
                timezone_choices=TIMEZONE_CHOICES,
                timezone_labels=TIMEZONE_LABELS,
                selected_timezone=user.timezone or default_tz,
                default_timezone=default_tz,
            )
    
    # Handle POST requests
    if request.method == "POST":
        with transaction_scope() as db:
            user = db.get(User, user_id)
            if not user:
                flash("User not found.", "danger"); return redirect(url_for("admin.users_list"))

            roles = db.execute(select(Role).order_by(Role.name.asc())).scalars().all()
            hospitals = db.execute(select(Hospital).order_by(Hospital.name.asc())).scalars().all()
            lab_units = db.execute(select(LabUnit).options(selectinload(LabUnit.hospital)).order_by(LabUnit.name.asc())).scalars().all()
            # Handle role assignments
            if "save_roles" in request.form:
                selected_roles = set(request.form.getlist("roles"))
                # Normalize role names to ones that exist in DB (ignore stray/unknown values)
                valid_role_names = {r.name for r in roles}
                selected_roles &= valid_role_names

                existing = {r.name for r in (user.roles or [])}
                will_remove = existing - selected_roles
                will_add = selected_roles - existing

                # Ensure at least one ACTIVE admin remains after this change
                if "admin" in existing and "admin" not in selected_roles and user.is_active:
                    active_admins = db.execute(
                        select(func.count(User.id))
                        .join(User.roles)
                        .where(Role.name == "admin", User.is_active.is_(True), User.id != user.id)
                    ).scalar_one() or 0
                    
                    if active_admins < 1:
                        flash("There must be at least one active admin user.", "warning")
                        default_tz = current_app.config.get("DEFAULT_DISPLAY_TIMEZONE", DEFAULT_TIMEZONE)
                        return render_template(
                            "admin/edit_user.html",
                            user=user,
                            roles=roles,
                            hospitals=hospitals,
                            lab_units=lab_units,
                            selected_lab_units={lu.id for lu in user.lab_units},
                            timezone_choices=TIMEZONE_CHOICES,
                            timezone_labels=TIMEZONE_LABELS,
                            selected_timezone=user.timezone or default_tz,
                            default_timezone=default_tz,
                        )

                # remove roles
                if user.roles:
                    user.roles[:] = [r for r in user.roles if r.name not in will_remove]

                # add roles
                if will_add:
                    add_objs = db.execute(select(Role).where(Role.name.in_(will_add))).scalars().all()
                    for r in add_objs:
                        user.roles.append(r)

                db.add(user)
                flash("Roles updated.", "success")
                return redirect(url_for("admin.edit_user", user_id=user_id))

            # Handle profile updates (including is_active)
            full_name = (request.form.get("full_name") or "").strip()
            designation = (request.form.get("designation") or "").strip()
            email = (request.form.get("email") or "").strip()
            phone = (request.form.get("phone") or "").strip()
            timezone_pref = (request.form.get("timezone") or "").strip()
            yj = (request.form.get("year_of_joining") or "").strip()
            ldos = (request.form.get("last_date_of_service") or "").strip()
            file_upload_quota = int(request.form.get("file_upload_quota") or 0)
            is_active = bool(request.form.get("is_active"))
            selected_lab_unit_ids = set(int(x) for x in request.form.getlist("lab_units"))
            default_tz = current_app.config.get("DEFAULT_DISPLAY_TIMEZONE", DEFAULT_TIMEZONE)

            def render_profile_error(message: str | None = None):
                if message:
                    flash(message, "danger")
                return render_template(
                    "admin/edit_user.html",
                    user=user,
                    roles=roles,
                    hospitals=hospitals,
                    lab_units=lab_units,
                    selected_lab_units={lu.id for lu in user.lab_units},
                    timezone_choices=TIMEZONE_CHOICES,
                    timezone_labels=TIMEZONE_LABELS,
                    selected_timezone=timezone_pref or default_tz,
                    default_timezone=default_tz,
                )

            # Check if we're trying to deactivate an admin user
            if user.is_active and not is_active:
                is_admin = "admin" in {r.name for r in (user.roles or [])}
                if is_admin:
                    active_admins = db.execute(
                        select(func.count(User.id))
                        .join(User.roles)
                        .where(Role.name == "admin", User.is_active.is_(True), User.id != user.id)
                    ).scalar_one() or 0

                    if active_admins < 1:
                        flash("There must be at least one active admin user.", "warning")
                        return render_profile_error()

            ok, msg = validate_email(email)
            if not ok:
                return render_profile_error(msg)

            ok, msg = validate_phone(phone)
            if not ok:
                return render_profile_error(msg)

            if timezone_pref and timezone_pref not in TIMEZONE_VALUES:
                return render_profile_error("Please select a valid timezone.")

            yj_int = None
            if yj:
                current_year = date.today().year
                if not yj.isdigit() or not (1970 <= int(yj) <= current_year + 1):
                    return render_profile_error("Year of joining must be a valid year.")
                yj_int = int(yj)

            ok, msg, ldos_date = parse_iso_date(ldos)
            if not ok:
                return render_profile_error(msg)

            if file_upload_quota < 0:
                return render_profile_error("File upload quota cannot be negative.")

            user.full_name = full_name or None
            user.designation = designation or None
            user.email = email or None
            user.phone = phone or None
            user.timezone = timezone_pref or default_tz
            user.year_of_joining = yj_int
            user.last_date_of_service = ldos_date
            user.file_upload_quota = file_upload_quota
            user.is_active = is_active

            # Update lab units
            user.lab_units.clear()
            if selected_lab_unit_ids:
                lab_unit_objs = db.execute(select(LabUnit).where(LabUnit.id.in_(selected_lab_unit_ids))).scalars().all()
                for lu in lab_unit_objs:
                    user.lab_units.append(lu)

            db.add(user)
            flash("Profile updated.", "success")
            return redirect(url_for("admin.users_list"))


def users_update(user_id: int):
    """
    Update a user's active flag from the users list.
    Prevents self-deactivation and prevents removing/deactivating the last active admin.
    """
    new_active = bool(request.form.get("active"))             # checkbox present -> True

    with transaction_scope() as db:
        user = db.get(User, user_id)
        if not user:
            flash("User not found.", "danger")
            return redirect(url_for("admin.users_list"))

        # 1) Don't let an admin deactivate themselves
        if user.id == getattr(current_user, "id", None) and not new_active:
            flash("You cannot deactivate your own account.", "warning")
            return redirect(url_for("admin.users_list"))

        # 2) Ensure at least one ACTIVE admin remains after this change
        active_admins = db.execute(
            select(func.count(User.id))
            .join(User.roles)
            .where(Role.name == "admin", User.is_active.is_(True))
        ).scalar_one() or 0

        is_admin_before = ("admin" in {r.name for r in (user.roles or [])}) and bool(user.is_active)

        if is_admin_before and not new_active:
            # This change would deactivate an active admin account.
            if active_admins <= 1:
                flash("There must be at least one active admin user.", "warning")
                return redirect(url_for("admin.users_list"))

        # 3) Apply changes
        user.is_active = new_active

        db.add(user)

        try:
            current_app.logger.info(
                "Admin '%s' updated user '%s': active=%s",
                getattr(current_user, "username", "unknown"),
                user.username,
                user.is_active,
            )
        except Exception:
            pass

    flash("User updated.", "success")
    return redirect(url_for("admin.users_list"))
