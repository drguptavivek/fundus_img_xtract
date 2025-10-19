"""Admin routes for managing rate limits."""

import logging
from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user

from utils.rate_limiter import clear_rate_limit, get_rate_limit_status, get_rate_limit_key
from auth.roles import roles_required

# Create blueprint
rate_limit_admin_bp = Blueprint("rate_limit_admin", __name__, url_prefix="/admin/rate-limits")

# Logger
rate_limit_logger = logging.getLogger("rate_limit")


@rate_limit_admin_bp.route("/")
@login_required
@roles_required("admin")
def index():
    """Rate limit management dashboard."""
    # Get overall statistics
    stats = get_rate_limit_status()
    
    return render_template(
        "admin/rate_limits/index.html",
        stats=stats,
        active_page="rate_limits"
    )


@rate_limit_admin_bp.route("/clear", methods=["POST"])
@login_required
@roles_required("admin")
def clear_limit():
    """Clear a rate limit block."""
    key = request.form.get("key", "").strip()
    limit = request.form.get("limit", "").strip()
    
    if not key:
        flash("Key is required to clear a rate limit", "error")
        return redirect(url_for("rate_limit_admin.index"))
    
    # Log the action
    rate_limit_logger.info(
        f"Admin {current_user.username} ({current_user.id}) attempting to clear rate limit "
        f"for key: {key}, limit: {limit or 'ALL'}"
    )
    
    # Attempt to clear the rate limit
    success = clear_rate_limit(key=key if key else None, limit=limit if limit else None)
    
    if success:
        flash(f"Rate limit cleared successfully for key: {key}", "success")
        rate_limit_logger.info(
            f"Admin {current_user.username} ({current_user.id}) successfully cleared rate limit "
            f"for key: {key}, limit: {limit or 'ALL'}"
        )
    else:
        flash("Failed to clear rate limit. Check logs for details.", "error")
        rate_limit_logger.error(
            f"Admin {current_user.username} ({current_user.id}) failed to clear rate limit "
            f"for key: {key}, limit: {limit or 'ALL'}"
        )
    
    return redirect(url_for("rate_limit_admin.index"))


@rate_limit_admin_bp.route("/status")
@login_required
@roles_required("admin")
def status():
    """Get rate limit status as JSON."""
    key = request.args.get("key")
    
    status_data = get_rate_limit_status(key=key)
    
    return jsonify(status_data)


@rate_limit_admin_bp.route("/my-key")
@login_required
def get_my_key():
    """Get the current user's rate limit key."""
    user_key = get_rate_limit_key()
    return jsonify({"key": user_key})


@rate_limit_admin_bp.route("/clear-all", methods=["POST"])
@login_required
@roles_required("admin")
def clear_all():
    """Clear ALL rate limits (dangerous operation)."""
    # Require confirmation
    confirm = request.form.get("confirm")
    if confirm != "CLEAR_ALL_RATE_LIMITS":
        flash("Invalid confirmation. Rate limits not cleared.", "error")
        return redirect(url_for("rate_limit_admin.index"))
    
    # Log the dangerous action
    rate_limit_logger.warning(
        f"Admin {current_user.username} ({current_user.id}) attempting to clear ALL rate limits!"
    )
    
    # Attempt to clear all rate limits
    success = clear_rate_limit()
    
    if success:
        flash("ALL rate limits have been cleared.", "warning")
        rate_limit_logger.warning(
            f"Admin {current_user.username} ({current_user.id}) successfully cleared ALL rate limits"
        )
    else:
        flash("Failed to clear all rate limits. Check logs for details.", "error")
        rate_limit_logger.error(
            f"Admin {current_user.username} ({current_user.id}) failed to clear ALL rate limits"
        )
    
    return redirect(url_for("rate_limit_admin.index"))