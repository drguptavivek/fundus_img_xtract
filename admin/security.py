import re
import os
from flask import render_template, request, redirect, url_for, flash, current_app
from sqlalchemy import select, func
from flask_login import current_user
from auth.roles import roles_required
from auth.security import hash_password, generate_strong_password
from utils.emails import send_password_reset_email
from auth.route_analyzer import analyze_all_routes, get_role_usage_statistics, get_routes_by_role
from models import User, Role
from db_transaction_manager import transaction_scope, get_db_session
from utils.log_sanitize import sanitize_log_value


def change_password():
    """
    Admin can change any user's password by username (case-insensitive).
    Lockout is cleared after reset.
    """
    def render_password_form(
        user_id: int | None,
        username: str,
        email: str,
        generated_password: str | None = None,
    ):
        if request.headers.get("HX-Request") or request.args.get("format") == "partial":
            return render_template(
                "admin/partials/user_password_edit.html",
                user_id=user_id,
                username=username,
                email=email,
                generated_password=generated_password,
            )
        return render_template("admin/change_password.html", username=username, email=email)

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()

        # Basic validation
        if not username:
            flash("Username is required.", "danger")
            return render_password_form(None, username, "")

        with transaction_scope() as db:
            user = db.execute(
                select(User).where(func.lower(User.username) == username.lower())
            ).scalar_one_or_none()

            if not user:
                flash("User not found.", "danger")
                return render_password_form(None, username, "")

            generated_password = generate_strong_password()
            user.password_hash = hash_password(generated_password)
            user.is_locked_until = None  # optional: clear any lockouts
            db.add(user)

            email = user.email or ""
            user_id = user.id

        if email:
            send_password_reset_email(email, username, generated_password)

        if request.headers.get("HX-Request") or request.args.get("format") == "partial":
            if email:
                flash(f"Password updated for '{username}' and emailed to the user.", "success")
                return redirect(url_for("admin.user_detail", user_id=user_id, format="shell"))
            flash(
                "Password reset. This user has no email address; copy the password and convey it securely.",
                "warning",
            )
            return render_password_form(user_id, username, email, generated_password)

        return render_template(
            "admin/password_reset_done.html",
            info={
                "username": username,
                "email": email,
                "password": generated_password,
            },
        )

        # Audit (no secrets)
        try:
            current_app.logger.info(
                "Admin '%s' changed password for user '%s'",
                getattr(current_user, "username", "unknown"),
                username,
            )
        except Exception as e:
            current_app.logger.warning("Audit logging failed: %s", sanitize_log_value(e))

        flash(f"Password updated for '{username}'.", "success")
        return redirect(url_for("admin.change_password", username=username))

    # GET
    username = (request.args.get("username") or "").strip()
    email = ""
    user_id = None
    if username:
        with get_db_session() as db:
            user = db.execute(
                select(User).where(func.lower(User.username) == username.lower())
            ).scalar_one_or_none()
            if user:
                email = user.email or ""
                user_id = user.id
            else:
                flash("User not found.", "danger")
    return render_password_form(user_id, username, email)


def manage_roles():
    """
    Show all roles.
    Note: Roles cannot be created through the UI as they must be defined in code.
    """
    # GET: show current roles
    with get_db_session() as db:
        roles = db.execute(select(Role).order_by(Role.name.asc())).scalars().all()
        
        # Render template within the same session to avoid detached instance errors
        return render_template("admin/roles.html", roles=roles)


@roles_required("admin")
def role_usage():
    """
    Show role usage statistics and which routes require which roles.
    """
    # Analyze all routes
    routes_info = analyze_all_routes()
    
    # Get role usage statistics
    role_stats = get_role_usage_statistics(routes_info)
    
    # Get all roles from database
    with get_db_session() as db:
        all_roles = [role.name for role in db.execute(select(Role)).scalars().all()]
        
        # Sort routes by file and function name
        routes_info.sort(key=lambda x: (x['file'], x['function']))
        
        # Render template within the same session to avoid detached instance errors
        return render_template(
            "admin/role_usage.html",
            routes_info=routes_info,
            role_stats=role_stats,
            all_roles=all_roles
        )


@roles_required("admin")
def routes_by_role(role_name):
    """
    Show all routes that require a specific role.
    """
    # Analyze all routes
    routes_info = analyze_all_routes()
    
    # Filter routes by role
    matching_routes = get_routes_by_role(routes_info, role_name)
    
    # Sort routes by file and function name
    matching_routes.sort(key=lambda x: (x['file'], x['function']))
    
    # Get all roles from database
    with get_db_session() as db:
        all_roles = [role.name for role in db.execute(select(Role)).scalars().all()]
        
        # Render template within the same session to avoid detached instance errors
        return render_template(
            "admin/routes_by_role.html",
            role_name=role_name,
            routes_info=matching_routes,
            all_roles=all_roles
        )
