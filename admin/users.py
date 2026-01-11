from datetime import date
from flask import render_template, request, redirect, url_for, flash, current_app, session
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from flask_login import current_user
from auth.roles import roles_required
from auth.security import (
    hash_password,
    check_password_strength,
    validate_username,
    validate_email,
    validate_phone,
    parse_iso_date,
    generate_strong_password,
)
from utils.emails import send_email_sync
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
        query = select(User).options(
            selectinload(User.roles), 
            selectinload(User.lab_units).selectinload(LabUnit.hospital)
        ).order_by(User.username.asc())
        
        # Site Admin Enforcement: Only show users in own hospital
        if not getattr(current_user, 'is_master_admin', False) and getattr(current_user, 'hospital_id', None):
            query = query.where(User.hospital_id == current_user.hospital_id)
            
        users = db.execute(query).scalars().all()
        
        # Render template within the same session to avoid detached instance errors
        return render_template("admin/users.html", users=users)

def _default_last_date_of_service(created_on: date) -> date:
    """
    Return a date two years after the provided date, handling leap days.
    """
    try:
        return created_on.replace(year=created_on.year + 2)
    except ValueError:
        return created_on.replace(month=2, day=28, year=created_on.year + 2)

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
    default_ldos = _default_last_date_of_service(date.today())
    default_ldos_str = default_ldos.isoformat()
    pre_ldos = (request.form.get("last_date_of_service") or "").strip()
    if request.method != "POST" and not pre_ldos:
        pre_ldos = default_ldos_str
    pre_file_upload_quota = int(request.form.get("file_upload_quota") or 0) if request.method == "POST" else 0
    pre_lab_unit_ids = set(int(x) for x in request.form.getlist("lab_units")) if request.method == "POST" else set()

    if request.method == "POST":
        username = pre_username
        password = generate_strong_password(12)
        default_tz = current_app.config.get("DEFAULT_DISPLAY_TIMEZONE", DEFAULT_TIMEZONE)

        ok, msg = validate_username(username)
        if not ok: return _add_user_err(msg, None, None, None, username, pre_active, pre_roles,
                                        pre_full_name, pre_phone, pre_designation, pre_email, pre_yj, pre_ldos or default_ldos_str,
                                        pre_file_upload_quota, pre_lab_unit_ids, pre_timezone)

        ok, msg = check_password_strength(password, min_len=10)
        if not ok: return _add_user_err(msg, None, None, None, username, pre_active, pre_roles,
                                        pre_full_name, pre_phone, pre_designation, pre_email, pre_yj, pre_ldos or default_ldos_str,
                                 pre_file_upload_quota, pre_lab_unit_ids, pre_timezone)

        ok, msg = validate_email(pre_email)
        if not ok: return _add_user_err(msg, None, None, None, username, pre_active, pre_roles,
                                        pre_full_name, pre_phone, pre_designation, pre_email, pre_yj, pre_ldos or default_ldos_str,
                                        pre_file_upload_quota, pre_lab_unit_ids, pre_timezone)

        ok, msg = validate_phone(pre_phone)
        if not ok: return _add_user_err(msg, None, None, None, username, pre_active, pre_roles,
                                        pre_full_name, pre_phone, pre_designation, pre_email, pre_yj, pre_ldos or default_ldos_str,
                                        pre_file_upload_quota, pre_lab_unit_ids, pre_timezone)

        if pre_timezone and pre_timezone not in TIMEZONE_VALUES:
            return _add_user_err("Please select a valid timezone.", None, None, None, username, pre_active, pre_roles,
                                 pre_full_name, pre_phone, pre_designation, pre_email, pre_yj, pre_ldos or default_ldos_str,
                                 pre_file_upload_quota, pre_lab_unit_ids, pre_timezone)

        yj_int = None
        if pre_yj:
            current_year = date.today().year
            if not pre_yj.isdigit() or not (1970 <= int(pre_yj) <= current_year + 1):
                return _add_user_err("Year of joining must be a valid year.", None, None, None, username, pre_active, pre_roles,
                                      pre_full_name, pre_phone, pre_designation, pre_email, pre_yj, pre_ldos or default_ldos_str,
                                      pre_file_upload_quota, pre_lab_unit_ids, pre_timezone)
            yj_int = int(pre_yj)

        if pre_ldos:
            ok, msg, ldos_date = parse_iso_date(pre_ldos)
            if not ok:
                return _add_user_err(msg, None, None, None, username, pre_active, pre_roles,
                                     pre_full_name, pre_phone, pre_designation, pre_email, pre_yj, pre_ldos,
                                     pre_file_upload_quota, pre_lab_unit_ids, pre_timezone)
        else:
            ldos_date = default_ldos

        if pre_file_upload_quota < 0:
            return _add_user_err("File upload quota cannot be negative.", None, None, None, username, pre_active, pre_roles,
                                 pre_full_name, pre_phone, pre_designation, pre_email, pre_yj, pre_ldos or default_ldos_str,
                                 pre_file_upload_quota, pre_lab_unit_ids, pre_timezone)

        with transaction_scope() as db:
            exists = db.execute(
                select(User).where(func.lower(User.username) == username.lower())
            ).scalar_one_or_none()
            if exists:
                return _add_user_err("Username already exists.", None, None, None, username, pre_active, pre_roles,
                                     pre_full_name, pre_phone, pre_designation, pre_email, pre_yj, pre_ldos or default_ldos_str,
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
                hospital_id=None if getattr(current_user, 'is_master_admin', False) else current_user.hospital_id
            )
            
            # Site Admin Enforcement: Prevent creating Master Admin
            if not getattr(current_user, 'is_master_admin', False):
                if "admin" in pre_roles:
                     # This validation happens deep inside transaction, so rolling back is automatic if we raise or return error.
                     # But we are in a 'with transaction_scope' block which auto-commits on exit.
                     # We should return error before db.add(user).
                     pass # handled below before adding roles
            
            db.add(user)

            if pre_roles:
                # Site Admin Enforcement: Check restricted roles
                if not getattr(current_user, 'is_master_admin', False):
                    if "admin" in pre_roles:
                         return _add_user_err("You cannot assign the Master Admin role.", None, None, None, username, pre_active, pre_roles,
                                      pre_full_name, pre_phone, pre_designation, pre_email, pre_yj, pre_ldos or default_ldos_str,
                                      pre_file_upload_quota, pre_lab_unit_ids, pre_timezone)

                role_objs = db.execute(select(Role).where(Role.name.in_(pre_roles))).scalars().all()
                for r in role_objs: user.roles.append(r)

            if pre_lab_unit_ids:
                lab_unit_objs = db.execute(select(LabUnit).where(LabUnit.id.in_(pre_lab_unit_ids))).scalars().all()
                for lu in lab_unit_objs: user.lab_units.append(lu)

        email_sent = None
        if pre_email:
            subject = "Your Eye Image Manager account"
            login_url = url_for("auth.login", _external=True)
            body = f"""
Hello {pre_full_name or username},

Your Eye Image Manager account has been created.

Username: {username}
Password: {password}
Login: {login_url}

Please keep this information secure.
"""
            email_sent = send_email_sync(pre_email, subject, body)

        session["user_created_info"] = {
            "username": username,
            "password": password,
            "email": pre_email or "",
            "email_sent": bool(email_sent) if pre_email else None,
        }
        return redirect(url_for("admin.user_created"))

    # Fetch roles, hospitals, and lab_units in the same session that will be used for rendering
    with get_db_session() as db:
        roles = db.execute(select(Role).order_by(Role.name.asc())).scalars().all()
        hospitals = db.execute(select(Hospital).order_by(Hospital.name.asc())).scalars().all()
        lab_units = db.execute(select(LabUnit).options(selectinload(LabUnit.hospital)).order_by(LabUnit.name.asc())).scalars().all()
        
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
    
    # Fetch fresh data in a new session to avoid detached instance errors
    with get_db_session() as db:
        roles = db.execute(select(Role).order_by(Role.name.asc())).scalars().all()
        hospitals = db.execute(select(Hospital).order_by(Hospital.name.asc())).scalars().all()
        lab_units = db.execute(select(LabUnit).options(selectinload(LabUnit.hospital)).order_by(LabUnit.name.asc())).scalars().all()
        
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


def user_created():
    info = session.pop("user_created_info", None)
    if not info:
        flash("No recent user creation details found.", "warning")
        return redirect(url_for("admin.users_list"))

    if info.get("email"):
        if info.get("email_sent") is True:
            flash(f"Account details sent to {info['email']}.", "info")
        elif info.get("email_sent") is False:
            flash(f"Failed to send account details to {info['email']}.", "warning")

    return render_template("admin/user_created.html", info=info)


def edit_user(user_id: int):
    # Handle GET request (display the form)
    with get_db_session() as db:
        user = db.get(User, user_id)
        if not user:
            flash("User not found.", "danger"); return redirect(url_for("admin.users_list"))
            
        # Site Admin Enforcement: Cannot edit users from other hospitals (or system users like AI models)
        if not getattr(current_user, 'is_master_admin', False):
             if getattr(user, 'hospital_id', None) != current_user.hospital_id:
                 flash("You do not have permission to edit this user.", "danger")
                 return redirect(url_for("admin.users_list"))

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
