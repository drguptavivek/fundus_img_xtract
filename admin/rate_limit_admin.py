"""Admin routes for managing rate limits."""

import logging
from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user

from utils.rate_limiter import clear_rate_limit, get_rate_limit_status, get_rate_limit_key, limiter
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
    # Get pagination parameters
    page = request.args.get('page', 1, type=int)
    per_page = 50
    
    # Get overall statistics
    stats = get_rate_limit_status()
    
    # Get all rate limit keys with pagination
    limits_data = get_all_rate_limits(page=page, per_page=per_page)
    
    return render_template(
        "admin/rate_limits/index.html",
        stats=stats,
        limits=limits_data,
        active_page="rate_limits",
        current_page=page,
        per_page=per_page
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
    # Call the function to get the key
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


@rate_limit_admin_bp.route("/clear-limit-ajax", methods=["POST"])
@login_required
@roles_required("admin")
def clear_limit_ajax():
    """Clear a rate limit block via AJAX."""
    key = request.json.get("key", "").strip()
    
    if not key:
        return jsonify({"success": False, "message": "Key is required to clear a rate limit"}), 400
    
    # Log the action
    rate_limit_logger.info(
        f"Admin {current_user.username} ({current_user.id}) attempting to clear rate limit "
        f"for key: {key} via AJAX"
    )
    
    # Attempt to clear the rate limit
    success = clear_rate_limit(key=key)
    
    if success:
        rate_limit_logger.info(
            f"Admin {current_user.username} ({current_user.id}) successfully cleared rate limit "
            f"for key: {key} via AJAX"
        )
        return jsonify({"success": True, "message": f"Rate limit cleared successfully for key: {key}"})
    else:
        rate_limit_logger.error(
            f"Admin {current_user.username} ({current_user.id}) failed to clear rate limit "
            f"for key: {key} via AJAX"
        )
        return jsonify({"success": False, "message": "Failed to clear rate limit. Check logs for details."}), 500


def get_all_rate_limits(page=1, per_page=50):
    """
    Get all rate limit keys with pagination.
    
    Args:
        page: Page number (default: 1)
        per_page: Items per page (default: 50)
    
    Returns:
        dict: Paginated rate limit data
    """
    global limiter
    if not limiter or not limiter._storage:
        return {
            "error": "Rate limiter not initialized",
            "items": [],
            "total": 0,
            "pages": 0,
            "current_page": page,
            "per_page": per_page
        }
    
    try:
        # Check if we're using Redis storage
        if hasattr(limiter._storage, 'storage') or type(limiter._storage).__name__ == 'RedisStorage':
            # For Redis storage, use the Redis client directly
            redis_client = None
            if hasattr(limiter._storage, 'storage'):
                redis_client = limiter._storage.storage
            elif hasattr(limiter._storage, '_redis'):
                redis_client = limiter._storage._redis
            
            if redis_client:
                # Get all keys matching the rate limit pattern
                pattern = "LIMITS:LIMITER*"
                all_keys = redis_client.keys(pattern)
                
                # Sort keys for consistent ordering
                all_keys.sort()
                
                # Get total count
                total = len(all_keys)
                
                # Calculate pagination
                total_pages = (total + per_page - 1) // per_page
                start_idx = (page - 1) * per_page
                end_idx = start_idx + per_page
                
                # Get paginated keys
                paginated_keys = all_keys[start_idx:end_idx]
                
                # Get detailed info for each key
                items = []
                for key in paginated_keys:
                    # Decode key from bytes to string if needed
                    if isinstance(key, bytes):
                        key = key.decode('utf-8')
                    
                    # Parse the key to extract meaningful information
                    parsed = parse_rate_limit_key(key)
                    
                    # Get TTL and value if available
                    ttl = redis_client.ttl(key)
                    value = redis_client.get(key)
                    
                    item = {
                        "key": key,
                        "parsed": parsed,
                        "ttl": ttl,
                        "value": value.decode('utf-8') if value and isinstance(value, bytes) else str(value) if value else None
                    }
                    items.append(item)
                
                return {
                    "items": items,
                    "total": total,
                    "pages": total_pages,
                    "current_page": page,
                    "per_page": per_page,
                    "has_prev": page > 1,
                    "has_next": page < total_pages,
                    "prev_num": page - 1 if page > 1 else None,
                    "next_num": page + 1 if page < total_pages else None
                }
            else:
                return {
                    "error": "Could not access Redis client",
                    "items": [],
                    "total": 0,
                    "pages": 0,
                    "current_page": page,
                    "per_page": per_page
                }
        else:
            # For other storage backends (memory, etc.)
            if hasattr(limiter._storage, 'keys'):
                all_keys = list(limiter._storage.keys())
                all_keys.sort()
                
                total = len(all_keys)
                total_pages = (total + per_page - 1) // per_page
                start_idx = (page - 1) * per_page
                end_idx = start_idx + per_page
                
                paginated_keys = all_keys[start_idx:end_idx]
                
                items = []
                for key in paginated_keys:
                    parsed = parse_rate_limit_key(key)
                    value = limiter._storage.get(key, None)
                    
                    item = {
                        "key": key,
                        "parsed": parsed,
                        "ttl": None,  # Memory storage doesn't have TTL
                        "value": str(value) if value is not None else None
                    }
                    items.append(item)
                
                return {
                    "items": items,
                    "total": total,
                    "pages": total_pages,
                    "current_page": page,
                    "per_page": per_page,
                    "has_prev": page > 1,
                    "has_next": page < total_pages,
                    "prev_num": page - 1 if page > 1 else None,
                    "next_num": page + 1 if page < total_pages else None
                }
            else:
                return {
                    "error": "Storage backend does not support key listing",
                    "items": [],
                    "total": 0,
                    "pages": 0,
                    "current_page": page,
                    "per_page": per_page
                }
    
    except Exception as e:
        rate_limit_logger.error(f"Failed to get rate limits: {e}")
        return {
            "error": str(e),
            "items": [],
            "total": 0,
            "pages": 0,
            "current_page": page,
            "per_page": per_page
        }


def parse_rate_limit_key(key):
    """
    Parse a rate limit key to extract meaningful information.
    
    Args:
        key: The rate limit key (e.g., "LIMITS:LIMITER/ip:127.0.0.1/global/1000/1/hour")
    
    Returns:
        dict: Parsed information
    """
    try:
        # Flask-Limiter 4.0 key format: LIMITS:LIMITER/<key>/<endpoint>/<count>/<period>/<per>
        parts = key.split('/')
        
        if len(parts) >= 6 and parts[0].startswith('LIMITS:LIMITER'):
            # Extract the client key part
            client_key_part = parts[1]
            
            # Determine type (IP or User)
            if client_key_part.startswith('ip:'):
                client_type = 'IP'
                client_value = client_key_part[3:]  # Remove 'ip:' prefix
            elif client_key_part.startswith('user:'):
                client_type = 'User'
                client_value = client_key_part[5:]  # Remove 'user:' prefix
            else:
                client_type = 'Other'
                client_value = client_key_part
            
            # Extract other parts
            endpoint = parts[2] if len(parts) > 2 else 'Unknown'
            count = parts[3] if len(parts) > 3 else 'Unknown'
            period = parts[4] if len(parts) > 4 else 'Unknown'
            per = parts[5] if len(parts) > 5 else 'Unknown'
            
            # Handle global limits
            if endpoint == 'global':
                endpoint_display = 'Global Limit'
            else:
                endpoint_display = endpoint.replace('fundus_', '').replace('_', ' ').title()
            
            return {
                'client_type': client_type,
                'client_value': client_value,
                'client_key': client_key_part,  # Keep the full key (ip:127.0.0.1 or user:1)
                'endpoint': endpoint,
                'endpoint_display': endpoint_display,
                'limit': f"{count} per {period}",
                'count': count,
                'period': period,
                'per': per
            }
        else:
            # Fallback for unknown formats
            return {
                'client_type': 'Unknown',
                'client_value': key,
                'client_key': key,  # Keep the full key
                'endpoint': 'Unknown',
                'endpoint_display': 'Unknown',
                'limit': 'Unknown',
                'count': 'Unknown',
                'period': 'Unknown',
                'per': 'Unknown'
            }
    except Exception as e:
        rate_limit_logger.error(f"Failed to parse rate limit key {key}: {e}")
        return {
            'client_type': 'Error',
            'client_value': key,
            'client_key': key,  # Keep the full key
            'endpoint': 'Parse Error',
            'endpoint_display': 'Parse Error',
            'limit': 'Unknown',
            'count': 'Unknown',
            'period': 'Unknown',
            'per': 'Unknown'
        }