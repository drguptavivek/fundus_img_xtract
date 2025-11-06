import re
import os
from flask import render_template, request, redirect, url_for, flash, current_app
from sqlalchemy import select, func
from flask_login import current_user
from auth.roles import roles_required
from auth.security import hash_password, check_password_strength
from auth.route_analyzer import analyze_all_routes, get_role_usage_statistics, get_routes_by_role
from models import User, Role
from db_transaction_manager import transaction_scope, get_db_session


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
        with transaction_scope() as db:
            user = db.execute(
                select(User).where(func.lower(User.username) == username.lower())
            ).scalar_one_or_none()

            if not user:
                flash("User not found.", "danger")
                return render_template("admin/change_password.html", username=username)

            user.password_hash = hash_password(new_pw)
            user.is_locked_until = None  # optional: clear any lockouts
            db.add(user)

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
    Show all roles.
    Note: Roles cannot be created through the UI as they must be defined in code.
    """
    # GET: show current roles
    with get_db_session() as db:
        roles = db.execute(select(Role).order_by(Role.name.asc())).scalars().all()
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
    
    return render_template(
        "admin/routes_by_role.html",
        role_name=role_name,
        routes_info=matching_routes,
        all_roles=all_roles
    )