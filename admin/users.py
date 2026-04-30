from datetime import date
from flask import render_template, request, redirect, url_for, flash, current_app, session
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from flask_login import current_user
from auth.roles import roles_required
from auth.utils import utcnow
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
from utils.log_sanitize import sanitize_log_value
from models import (
    User,
    Role,
    Hospital,
    LabUnit,
    UserDiseaseUnitRole,
    ProjectInvestigator,
    UploadMapping,
    UploadMappingCamera,
    UploadMappingArea,
    MobileAuthSession,
    LoginAttempt,
)
from db_transaction_manager import transaction_scope, get_db_session
from utils.timezone_choices import (
    TIMEZONE_CHOICES,
    TIMEZONE_VALUES,
    TIMEZONE_LABELS,
    DEFAULT_TIMEZONE,
)
from app_cache import cache


def _can_access_user_detail(target_user: User) -> bool:
    """Return whether the current user may view this user's admin detail hub."""
    user_roles = {r.name for r in (current_user.roles or [])}
    if "admin" in user_roles:
        return True

    current_hospital_id = getattr(current_user, "hospital_id", None)
    target_hospital_id = getattr(target_user, "hospital_id", None)
    return bool(current_hospital_id) and target_hospital_id == current_hospital_id


def _group_lab_units_by_hospital(lab_units: list[LabUnit]) -> list[dict]:
    grouped: dict[str, list[str]] = {}
    for lab_unit in lab_units:
        hospital_name = lab_unit.hospital.name if lab_unit.hospital else "Unknown Hospital"
        grouped.setdefault(hospital_name, []).append(lab_unit.name)
    return [
        {"hospital_name": hospital_name, "lab_units": sorted(unit_names)}
        for hospital_name, unit_names in sorted(grouped.items(), key=lambda item: item[0].lower())
    ]


def _build_user_detail_context(db, user_id: int) -> dict | None:
    """Load the canonical user detail hub payload."""
    user = db.execute(
        select(User)
        .options(
            selectinload(User.roles),
            selectinload(User.hospital),
            selectinload(User.lab_units).selectinload(LabUnit.hospital),
            selectinload(User.mobile_auth_sessions),
        )
        .where(User.id == user_id)
    ).scalar_one_or_none()
    if not user or not _can_access_user_detail(user):
        return None

    grading_rows = db.execute(
        select(UserDiseaseUnitRole)
        .options(
            selectinload(UserDiseaseUnitRole.disease),
            selectinload(UserDiseaseUnitRole.lab_unit).selectinload(LabUnit.hospital),
        )
        .where(UserDiseaseUnitRole.user_id == user_id)
        .order_by(UserDiseaseUnitRole.active.desc(), UserDiseaseUnitRole.lab_unit_id.asc(), UserDiseaseUnitRole.disease_id.asc())
    ).scalars().all()

    investigator_rows = db.execute(
        select(ProjectInvestigator)
        .options(selectinload(ProjectInvestigator.project))
        .where(ProjectInvestigator.user_id == user_id)
        .order_by(ProjectInvestigator.active.desc(), ProjectInvestigator.project_id.asc())
    ).scalars().all()

    mapping_rows = db.execute(
        select(UploadMapping)
        .options(
            selectinload(UploadMapping.project),
            selectinload(UploadMapping.lab_unit).selectinload(LabUnit.hospital),
            selectinload(UploadMapping.disease),
            selectinload(UploadMapping.default_disease),
            selectinload(UploadMapping.cameras).selectinload(UploadMappingCamera.camera),
            selectinload(UploadMapping.areas).selectinload(UploadMappingArea.area),
        )
        .where(UploadMapping.user_id == user_id)
        .order_by(UploadMapping.active.desc(), UploadMapping.project_id.asc(), UploadMapping.lab_unit_id.asc(), UploadMapping.disease_id.asc())
    ).scalars().all()

    login_attempts = db.execute(
        select(LoginAttempt)
        .where(func.lower(LoginAttempt.username_input) == user.username.lower())
        .order_by(LoginAttempt.created_at.desc())
        .limit(10)
    ).scalars().all()

    mobile_sessions = sorted(
        list(user.mobile_auth_sessions or []),
        key=lambda item: item.created_at,
        reverse=True,
    )

    return {
        "user": user,
        "roles": [role.name for role in (user.roles or [])],
        "grouped_lab_units": _group_lab_units_by_hospital(list(user.lab_units or [])),
        "grading_rows": grading_rows,
        "investigator_rows": investigator_rows,
        "mapping_rows": mapping_rows,
        "login_attempts": login_attempts,
        "mobile_sessions": mobile_sessions,
    }


def _render_user_hub_section(context: dict, tab: str):
    """Render a specific user-hub section or editor fragment."""
    render_context = dict(context)
    render_context.pop("tab", None)
    normalized_tab = (tab or "overview").strip().lower()
    if normalized_tab not in {
        "overview",
        "access",
        "grading",
        "uploads",
        "sessions",
        "activity",
        "profile-edit",
        "grading-edit",
        "password-edit",
    }:
        normalized_tab = "overview"

    if normalized_tab == "profile-edit":
        return render_template("admin/partials/user_profile_edit.html", **render_context)
    if normalized_tab == "grading-edit":
        return render_template("admin/partials/user_grading_edit.html", **render_context)
    if normalized_tab == "password-edit":
        return render_template("admin/partials/user_password_edit.html", **render_context)
    return render_template("admin/partials/user_hub_section.html", tab=normalized_tab, **render_context)


def users_list():
    """List all users with roles, hospitals, and lab units."""

    with get_db_session() as db:
        query = select(User).options(
            selectinload(User.roles), 
            selectinload(User.lab_units).selectinload(LabUnit.hospital)
        ).order_by(User.username.asc())
        
        # Keep local admins scoped to their hospital, but let admins see the full list.
        if current_user.has_role("local_admin") and not current_user.has_role("admin") and getattr(current_user, "hospital_id", None):
            query = query.where(User.hospital_id == current_user.hospital_id)
            
        users = db.execute(query).scalars().all()
        template_name = "admin/partials/user_list_workspace.html" if request.headers.get("HX-Request") or request.args.get("format") == "partial" else "admin/users.html"

        # Render template within the same session to avoid detached instance errors
        return render_template(template_name, users=users)


def user_detail(user_id: int):
    """Canonical admin user hub with all assignments and activity in one place."""
    with get_db_session() as db:
        context = _build_user_detail_context(db, user_id)
        if context is None:
            flash("User not found or not accessible.", "danger")
            return redirect(url_for("admin.users_list"))
        tab = request.args.get("tab") or "overview"
        render_mode = request.args.get("format")
        if render_mode == "shell":
            return render_template("admin/partials/user_hub_shell.html", tab=tab, **context)
        if request.headers.get("HX-Request") or render_mode == "partial":
            return _render_user_hub_section(context, tab)
        return render_template("admin/user_detail.html", tab=tab, **context)

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
                hospital_id=current_user.hospital_id
            )
            
            # Site Admin Enforcement: Prevent creating Master Admin
            if "admin" in pre_roles and not current_user.has_role("admin"):
                 # This validation happens deep inside transaction, so rolling back is automatic if we raise or return error.
                 # But we are in a 'with transaction_scope' block which auto-commits on exit.
                 # We should return error before db.add(user).
                 pass # handled below before adding roles
            
            db.add(user)

            if pre_roles:
                # Site Admin Enforcement: Check restricted roles
                if "admin" in pre_roles and not current_user.has_role("admin"):
                     return _add_user_err("You cannot assign the admin role.", None, None, None, username, pre_active, pre_roles,
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

        # Hospital isolation: admin sees all hospitals, local_admin sees only their own
        user_roles = {r.name for r in (current_user.roles or [])}
        if 'admin' in user_roles:
            hospitals = db.execute(select(Hospital).order_by(Hospital.name.asc())).scalars().all()
        else:
            hospitals = [db.get(Hospital, current_user.hospital_id)] if current_user.hospital_id else []

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

        # Hospital isolation: admin sees all hospitals, local_admin sees only their own
        user_roles = {r.name for r in (current_user.roles or [])}
        if 'admin' in user_roles:
            hospitals = db.execute(select(Hospital).order_by(Hospital.name.asc())).scalars().all()
        else:
            hospitals = [db.get(Hospital, current_user.hospital_id)] if current_user.hospital_id else []

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
        if not current_user.has_role("admin"):
             if getattr(user, 'hospital_id', None) != current_user.hospital_id:
                 flash("You do not have permission to edit this user.", "danger")
                 return redirect(url_for("admin.users_list"))

        roles = db.execute(select(Role).order_by(Role.name.asc())).scalars().all()

        # Hospital isolation: admin sees all hospitals, local_admin sees only their own
        user_roles = {r.name for r in (current_user.roles or [])}
        if 'admin' in user_roles:
            hospitals = db.execute(select(Hospital).order_by(Hospital.name.asc())).scalars().all()
        else:
            # local_admin or other roles only see their hospital
            hospitals = [db.get(Hospital, current_user.hospital_id)] if current_user.hospital_id else []

        lab_units = db.execute(select(LabUnit).options(selectinload(LabUnit.hospital)).order_by(LabUnit.name.asc())).scalars().all()

        # Convert lab units to dicts for JSON serialization
        lab_units_dict = [{'id': lu.id, 'name': lu.name, 'hospital_id': lu.hospital_id} for lu in lab_units]

        if request.method == "GET":
            default_tz = current_app.config.get("DEFAULT_DISPLAY_TIMEZONE", DEFAULT_TIMEZONE)
            if request.headers.get("HX-Request") or request.args.get("format") == "partial":
                return render_template(
                    "admin/partials/user_profile_edit.html",
                    user=user,
                    roles=roles,
                    hospitals=hospitals,
                    lab_units=lab_units_dict,
                    selected_lab_units=list(lu.id for lu in user.lab_units),
                    timezone_choices=TIMEZONE_CHOICES,
                    timezone_labels=TIMEZONE_LABELS,
                    selected_timezone=user.timezone or default_tz,
                    default_timezone=default_tz,
                )
            return render_template(
                "admin/edit_user.html",
                user=user,
                roles=roles,
                hospitals=hospitals,
                lab_units=lab_units_dict,
                selected_lab_units=list(lu.id for lu in user.lab_units),
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

            # Hospital isolation: admin sees all hospitals, local_admin sees only their own
            user_roles = {r.name for r in (current_user.roles or [])}
            if 'admin' in user_roles:
                hospitals = db.execute(select(Hospital).order_by(Hospital.name.asc())).scalars().all()
            else:
                # local_admin or other roles only see their hospital
                hospitals = [db.get(Hospital, current_user.hospital_id)] if current_user.hospital_id else []

            lab_units = db.execute(select(LabUnit).options(selectinload(LabUnit.hospital)).order_by(LabUnit.name.asc())).scalars().all()
            lab_units_dict = [{'id': lu.id, 'name': lu.name, 'hospital_id': lu.hospital_id} for lu in lab_units]
            # Handle role assignments
            if "save_roles" in request.form:
                selected_roles = set(request.form.getlist("roles"))
                # Normalize role names to ones that exist in DB (ignore stray/unknown values)
                valid_role_names = {r.name for r in roles}
                selected_roles &= valid_role_names

                existing = {r.name for r in (user.roles or [])}
                will_add = selected_roles - existing

                # add roles
                if will_add:
                    add_objs = db.execute(select(Role).where(Role.name.in_(will_add))).scalars().all()
                    for r in add_objs:
                        user.roles.append(r)

                if existing - selected_roles:
                    flash("Existing roles were preserved. This screen only adds roles.", "info")

                db.add(user)
                cache_key = f"auth:user:{user.id}"
                cache.delete(cache_key)
                flash("Roles updated.", "success")
                if request.headers.get("HX-Request") or request.args.get("format") == "partial":
                    return redirect(url_for("admin.user_detail", user_id=user_id, format="shell"))
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
            hospital_id = request.form.get("hospital_id")
            selected_lab_unit_ids = set(int(x) for x in request.form.getlist("lab_units"))
            default_tz = current_app.config.get("DEFAULT_DISPLAY_TIMEZONE", DEFAULT_TIMEZONE)

            def render_profile_error(message: str | None = None):
                if message:
                    flash(message, "danger")
                template_name = (
                    "admin/partials/user_profile_edit.html"
                    if request.headers.get("HX-Request") or request.args.get("format") == "partial"
                    else "admin/edit_user.html"
                )
                return render_template(
                    template_name,
                    user=user,
                    roles=roles,
                    hospitals=hospitals,
                    lab_units=lab_units_dict,
                    selected_lab_units=list(lu.id for lu in user.lab_units),
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

            # Hospital validation and assignment
            if not hospital_id:
                return render_profile_error("Hospital must be selected.")

            hospital_id = int(hospital_id)

            # Hospital isolation: admin can assign to any hospital, local_admin only to their own
            user_roles = {r.name for r in (current_user.roles or [])}
            if 'admin' not in user_roles:
                if hospital_id != current_user.hospital_id:
                    return render_profile_error("You can only assign users to your hospital.")

            # Hospital isolation: Verify all lab units belong to the selected hospital
            if selected_lab_unit_ids:
                lab_unit_objs = db.execute(
                    select(LabUnit).where(LabUnit.id.in_(selected_lab_unit_ids))
                ).scalars().all()
                for lu in lab_unit_objs:
                    if lu.hospital_id != hospital_id:
                        return render_profile_error(
                            f"Lab unit '{lu.name}' belongs to a different hospital. "
                            "Users can only be assigned lab units from their assigned hospital."
                        )

            user.full_name = full_name or None
            user.hospital_id = hospital_id
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
            if request.headers.get("HX-Request") or request.args.get("format") == "partial":
                return redirect(url_for("admin.user_detail", user_id=user_id, format="shell"))
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
        except Exception as e:
            current_app.logger.warning("Failed to log user update: %s", sanitize_log_value(e))

    flash("User updated.", "success")
    return redirect(url_for("admin.users_list"))


def revoke_mobile_session(user_id: int, session_id: str):
    """Revoke a mobile session from the admin user hub."""
    with transaction_scope() as db:
        user = db.get(User, user_id)
        if not user or not _can_access_user_detail(user):
            flash("User not found or not accessible.", "danger")
            return redirect(url_for("admin.users_list"))

        mobile_session = db.execute(
            select(MobileAuthSession)
            .where(MobileAuthSession.id == session_id)
            .where(MobileAuthSession.user_id == user_id)
        ).scalar_one_or_none()
        if mobile_session is None:
            flash("Mobile session not found.", "warning")
            return redirect(url_for("admin.user_detail", user_id=user_id))

        mobile_session.is_revoked = True
        mobile_session.revoked_at = utcnow()
        db.add(mobile_session)

    flash("Mobile session revoked.", "success")

    if request.headers.get("HX-Request") or request.args.get("format") == "shell":
        with get_db_session() as db:
            context = _build_user_detail_context(db, user_id)
            if context is None:
                flash("User not found or not accessible.", "danger")
                return redirect(url_for("admin.users_list"))
            return render_template("admin/partials/user_hub_shell.html", **context)

    return redirect(url_for("admin.user_detail", user_id=user_id))
