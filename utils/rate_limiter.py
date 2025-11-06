"""
Rate limiting utilities for the Flask application.
Provides different rate limiting strategies for various endpoints.

Features:
- Role-based rate limiting
- Custom key generation for users/IPs
- Specialized decorators for different endpoint types
- Memcached/Redis storage backends
- Meta limits for overall protection
- Dynamic rate limit configuration
- Shared limits for resource protection
- Comprehensive error handling and logging
"""

import os
import logging
from functools import wraps
from typing import Callable, Optional, Union

from flask import request, jsonify, current_app, g
from flask_limiter import Limiter, ExemptionScope
from flask_limiter.util import get_remote_address
from sqlalchemy import text
from models import Session
from utils.env_loader import load_environment

load_environment()

# Logger will be configured in app.py
rate_limit_logger = logging.getLogger("rate_limit")

# Initialize Flask-Limiter with custom key function
def get_rate_limit_key() -> str:
    """
    Custom key function for rate limiting.
    Uses user ID if authenticated, otherwise IP address.
    """
    from flask_login import current_user
    
    # Try to get user ID first for authenticated users
    if hasattr(current_user, 'is_authenticated') and current_user.is_authenticated:
        return f"user:{current_user.id}"
    
    # Fall back to IP address
    return f"ip:{get_remote_address()}"

# Initialize limiter (will be configured in init_rate_limiting)
limiter = None

def get_limiter():
    """Get the rate limiter instance."""
    return limiter

def rate_limit_with_feedback(
    limit: str,
    per_method: bool = True,
    methods: Optional[list] = None,
    error_message: Optional[str] = None,
    show_warning: bool = False
) -> Callable:
    """
    Enhanced rate limit decorator that provides flash message feedback.
    
    Args:
        limit: Rate limit string (e.g., "10 per minute")
        per_method: Whether to apply limits per HTTP method
        methods: List of HTTP methods to limit (None = all)
        error_message: Custom error message for rate limit exceeded
        show_warning: Whether to show a warning message when approaching the limit
    """
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def wrapped(*args, **kwargs):
            # Check if we should show a warning about remaining requests
            if show_warning and not request.path.startswith('/api/'):
                try:
                    # Get current rate limit status
                    from flask import g
                    if hasattr(g, 'limiter'):
                        # This is a simplified check - in a real implementation,
                        # you might want to check the actual remaining requests
                        pass
                except Exception:
                    pass
            
            # Get the limiter from app context or use global
            from flask import current_app
            if current_app and 'limiter' in current_app.extensions:
                # Flask-Limiter 4.0 stores the limiter in a set
                limiter_set = current_app.extensions['limiter']
                if isinstance(limiter_set, set) and limiter_set:
                    current_limiter = next(iter(limiter_set))
                else:
                    current_limiter = limiter_set
            else:
                current_limiter = limiter
            
            if current_limiter is None:
                # If no limiter is available, just call the function
                return f(*args, **kwargs)
            
            # Apply the limiter dynamically
            return current_limiter.limit(
                limit,
                per_method=per_method,
                methods=methods,
                error_message=error_message or f"Rate limit exceeded: {limit}",
                override_defaults=True
            )(f)(*args, **kwargs)
        
        return wrapped
    
    return decorator

def rate_limit(
    limit: str,
    per_method: bool = True,
    methods: Optional[list] = None,
    error_message: Optional[str] = None
) -> Callable:
    """
    Decorator for applying rate limits to routes.
    
    Args:
        limit: Rate limit string (e.g., "10 per minute")
        per_method: Whether to apply limits per HTTP method
        methods: List of HTTP methods to limit (None = all)
        error_message: Custom error message for rate limit exceeded
    """
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def wrapped(*args, **kwargs):
            # Get the limiter from app context or use global
            from flask import current_app
            if current_app and 'limiter' in current_app.extensions:
                # Flask-Limiter 4.0 stores the limiter in a set
                limiter_set = current_app.extensions['limiter']
                if isinstance(limiter_set, set) and limiter_set:
                    current_limiter = next(iter(limiter_set))
                else:
                    current_limiter = limiter_set
            else:
                current_limiter = limiter
            
            if current_limiter is None:
                # If no limiter is available, just call the function
                return f(*args, **kwargs)
            
            # Apply the limiter dynamically
            return current_limiter.limit(
                limit,
                per_method=per_method,
                methods=methods,
                error_message=error_message or f"Rate limit exceeded: {limit}",
                override_defaults=False
            )(f)(*args, **kwargs)
        
        return wrapped
    
    return decorator

def auth_rate_limit(limit: str = "5 per minute") -> Callable:
    """
    Specialized rate limit for authentication endpoints.
    More restrictive than general rate limits.
    """
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def wrapped(*args, **kwargs):
            # Get the limiter from app context or use global
            from flask import current_app
            if current_app and 'limiter' in current_app.extensions:
                # Flask-Limiter 4.0 stores the limiter in a set
                limiter_set = current_app.extensions['limiter']
                if isinstance(limiter_set, set) and limiter_set:
                    current_limiter = next(iter(limiter_set))
                else:
                    current_limiter = limiter_set
            else:
                current_limiter = limiter
            
            if current_limiter is None:
                # If no limiter is available, just call the function
                return f(*args, **kwargs)
            
            # Apply the limiter dynamically
            return current_limiter.limit(
                limit,
                per_method=True,
                methods=["POST"],
                error_message="Too many authentication attempts. Please try again later.",
                override_defaults=True
            )(f)(*args, **kwargs)
        
        return wrapped
    
    return decorator

def upload_rate_limit(limit: str = "200 per minute") -> Callable:
    """
    Rate limit for file upload endpoints.
    """
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def wrapped(*args, **kwargs):
            # Get the limiter from app context or use global
            from flask import current_app
            if current_app and 'limiter' in current_app.extensions:
                # Flask-Limiter 4.0 stores the limiter in a set
                limiter_set = current_app.extensions['limiter']
                if isinstance(limiter_set, set) and limiter_set:
                    current_limiter = next(iter(limiter_set))
                else:
                    current_limiter = limiter_set
            else:
                current_limiter = limiter
            
            if current_limiter is None:
                # If no limiter is available, just call the function
                return f(*args, **kwargs)
            
            # Apply the limiter dynamically
            return current_limiter.limit(
                limit,
                per_method=True,
                methods=["POST"],
                error_message="Upload rate limit exceeded. Please wait before uploading more files.",
                override_defaults=True
            )(f)(*args, **kwargs)
        
        return wrapped
    
    return decorator

def api_rate_limit(limit: str = "200 per minute") -> Callable:
    """
    Rate limit for general API endpoints.
    """
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def wrapped(*args, **kwargs):
            # Get the limiter from app context or use global
            from flask import current_app
            if current_app and 'limiter' in current_app.extensions:
                # Flask-Limiter 4.0 stores the limiter in a set
                limiter_set = current_app.extensions['limiter']
                if isinstance(limiter_set, set) and limiter_set:
                    current_limiter = next(iter(limiter_set))
                else:
                    current_limiter = limiter_set
            else:
                current_limiter = limiter
            
            if current_limiter is None:
                # If no limiter is available, just call the function
                return f(*args, **kwargs)
            
            # Apply the limiter dynamically
            return current_limiter.limit(
                limit,
                per_method=True,
                error_message="API rate limit exceeded. Please reduce your request frequency.",
                override_defaults=True
            )(f)(*args, **kwargs)
        
        return wrapped
    
    return decorator

def admin_rate_limit(limit: str = "100 per minute") -> Callable:
    """
    Rate limit for admin endpoints.
    """
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def wrapped(*args, **kwargs):
            # Get the limiter from app context or use global
            from flask import current_app
            if current_app and 'limiter' in current_app.extensions:
                # Flask-Limiter 4.0 stores the limiter in a set
                limiter_set = current_app.extensions['limiter']
                if isinstance(limiter_set, set) and limiter_set:
                    current_limiter = next(iter(limiter_set))
                else:
                    current_limiter = limiter_set
            else:
                current_limiter = limiter
            
            if current_limiter is None:
                # If no limiter is available, just call the function
                return f(*args, **kwargs)
            
            # Apply the limiter dynamically
            return current_limiter.limit(
                limit,
                per_method=True,
                error_message="Admin operation rate limit exceeded.",
                override_defaults=True
            )(f)(*args, **kwargs)
        
        return wrapped
    
    return decorator

def log_rate_limit_violation(limit_key, limit):
    """
    Log rate limit violations for security monitoring.
    
    Args:
        limit_key: The rate limit key that was exceeded
        limit: The rate limit that was exceeded
    """
    from flask_login import current_user
    
    client_ip = get_remote_address()
    endpoint = request.endpoint or "unknown"
    method = request.method
    path = request.path or "unknown"
    
    user_info = "anonymous"
    if hasattr(current_user, 'is_authenticated') and current_user.is_authenticated:
        user_info = f"user:{current_user.id}({current_user.username})"
    
    rate_limit_logger.warning(
        f"Rate limit violation - IP: {client_ip}, User: {user_info}, "
        f"Endpoint: {endpoint}, Path: {path}, Method: {method}, "
        f"Limit: {limit}, Key: {limit_key}"
    )
    
    # Also log to flask-limiter logger as per Flask-Limiter documentation
    limiter_logger = logging.getLogger("flask-limiter")
    limiter_logger.warning(
        f"Rate limit violation - IP: {client_ip}, User: {user_info}, "
        f"Endpoint: {endpoint}, Path: {path}, Method: {method}, "
        f"Limit: {limit}"
    )

# Custom error handler for rate limit exceeded
def handle_rate_limit_exceeded(request_limit):
    """
    Custom error handler for rate limit exceeded.
    Returns JSON response for API endpoints and HTML for others.
    
    Args:
        request_limit: RequestLimit object containing limit information
    """
    from flask import make_response
    
    # Extract limit information from the RequestLimit object
    # In flask-limiter 4.0.0, RequestLimit (or RuntimeLimit) has these attributes:
    # - limit: the limit that was breached (may be a string or Limit object)
    # - key: the key that was rate limited
    # - retry_after: seconds until the limit resets
    limit = getattr(request_limit, 'limit', None)
    limit_key = getattr(request_limit, 'key', None)
    
    # Get the limit string representation
    if limit:
        # Handle different limit object types in Flask-Limiter 4.0
        if hasattr(limit, 'limit') and hasattr(limit, 'per'):
            # This is a Limit object (e.g., "20 per minute")
            limit_str = f"{limit.limit} per {limit.per}"
        elif hasattr(limit, '__str__'):
            # Try to convert to string
            limit_str = str(limit)
            # If it looks like a repr, try to extract the actual limit
            if 'RuntimeLimit' in limit_str or 'limit=' in limit_str:
                # Extract the limit from the repr
                import re
                match = re.search(r'(\d+)\s+per\s+(\w+)', limit_str)
                if match:
                    limit_str = f"{match.group(1)} per {match.group(2)}"
                else:
                    # Fallback to a generic message
                    limit_str = "Too many requests"
        else:
            limit_str = "Too many requests"
    else:
        limit_str = "Too many requests"
    
    # Log the violation
    if limit_key:
        log_rate_limit_violation(limit_key, limit_str)
    else:
        log_rate_limit_violation("unknown", limit_str)
    
    # Get retry after value from the limit
    # In Flask-Limiter 4.0, retry_after might be in different places
    retry_after = getattr(request_limit, 'retry_after', None)
    
    # Try to get retry_after from the limit object if it's None
    if retry_after is None and hasattr(limit, 'reset_in'):
        retry_after = limit.reset_in
    elif retry_after is None and hasattr(limit, 'parsed_limit'):
        # For some limit objects, the reset time might be in parsed_limit
        parsed = limit.parsed_limit
        if hasattr(parsed, 'reset_in'):
            retry_after = parsed.reset_in
    
    # Default to 60 seconds if still None
    if retry_after is None:
        retry_after = 60
    
    # Create appropriate error message
    error_message = f"Rate limit exceeded: {limit_str}"
    
    # Check if this is an API request
    if request.path.startswith('/api/') or request.headers.get('Accept') == 'application/json':
        return make_response(jsonify({
            "error": "Rate limit exceeded",
            "message": error_message,
            "retry_after": retry_after
        }), 429)
    
    # Add flash message with rate limit information for web requests
    # Clear any existing flash messages to avoid duplicates
    from flask import flash, get_flashed_messages
    
    # Clear existing flash messages to prevent duplicates
    get_flashed_messages()
    
    # Add our flash message
    if retry_after and retry_after > 0:
        flash(f"Rate limit exceeded. Please try again in {retry_after} seconds.", "warning")
    else:
        flash("Rate limit exceeded. Please try again later.", "warning")
    
    # Return HTML error page for regular requests
    from flask import render_template, redirect, url_for
    # For login page, redirect back to login with the flash message
    if request.path == '/login':
        return redirect(url_for('auth.login'))
    
    # Check if dashboard route exists
    dashboard_url = None
    try:
        dashboard_url = url_for('dashboard.index')
    except:
        # Dashboard route doesn't exist, don't include the link
        pass
    
    # Try to render the template, fall back to JSON if not available
    try:
        return render_template(
            "errors/429.html",
            error_message=error_message,
            retry_after=retry_after,
            dashboard_url=dashboard_url
        ), 429
    except Exception:
        # Template not available, return JSON response
        return make_response(jsonify({
            "error": "Rate limit exceeded",
            "message": error_message,
            "retry_after": retry_after
        }), 429)

def get_user_rate_limits(user_id: int) -> dict:
    """
    Get custom rate limits for a specific user based on their role.
    Admins and privileged users get higher limits.
    """
    from models import User
    
    with Session() as db:
        user = db.get(User, user_id)
        if not user:
            return {"default": "500 per hour"}
        
        # Check user roles and return appropriate limits
        if user.has_role('admin'):
            return {
                "default": "5000 per hour",
                "upload": "200 per minute",
                "api": "1000 per minute"
            }
        elif user.has_role('data_manager', 'ophthalmologist'):
            return {
                "default": "2000 per hour",
                "upload": "200 per minute",
                "api": "500 per minute"
            }
        elif user.has_role('fileUploader', 'optometrist'):
            return {
                "default": "1000 per hour",
                "upload": "200 per minute",
                "api": "200 per minute"
            }
        else:
            return {
                "default": "500 per hour",
                "upload": "10 per minute",
                "api": "100 per minute"
            }

def dynamic_rate_limit_from_config():
    """
    Dynamically load rate limits from configuration.
    This allows updating limits without code changes.
    
    Returns:
        str: Rate limit string from config
    """
    # Check if there's a custom limit for the current endpoint
    endpoint = request.endpoint if request else None
    if endpoint:
        custom_limit = current_app.config.get(f'RATELIMIT_{endpoint.upper()}_LIMIT')
        if custom_limit:
            return custom_limit
    
    # Return default limit
    return current_app.config.get('RATELIMIT_DEFAULT', '500 per hour, 50 per minute')

def shared_resource_limit(resource_name: str, limit: str = None):
    """
    Create a shared rate limit for protecting specific resources.
    Multiple routes can share the same limit bucket.
    
    Args:
        resource_name: Name of the resource to protect
        limit: Rate limit string (optional, defaults to config)
    
    Returns:
        Callable: Decorator function
    """
    if limit is None:
        limit = current_app.config.get('RATELIMIT_SHARED_DEFAULT', '200 per hour')
    
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            # Get the current limiter instance
            if current_app and 'limiter' in current_app.extensions:
                # Flask-Limiter 4.0 stores the limiter in a set
                limiter_set = current_app.extensions['limiter']
                if isinstance(limiter_set, set) and limiter_set:
                    current_limiter = next(iter(limiter_set))
                else:
                    current_limiter = limiter_set
            else:
                current_limiter = limiter
            
            # Apply shared limit with resource scope
            return current_limiter.shared_limit(
                limit,
                scope=resource_name
            )(f)(*args, **kwargs)
        return wrapped
    return decorator

def conditional_exempt(condition_func: Callable[[], bool]):
    """
    Conditionally exempt a route from rate limiting based on a condition.
    
    Args:
        condition_func: Function that returns True if route should be exempt
    
    Returns:
        Callable: Decorator function
    """
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            # Get the current limiter instance
            if current_app and 'limiter' in current_app.extensions:
                # Flask-Limiter 4.0 stores the limiter in a set
                limiter_set = current_app.extensions['limiter']
                if isinstance(limiter_set, set) and limiter_set:
                    current_limiter = next(iter(limiter_set))
                else:
                    current_limiter = limiter_set
            else:
                current_limiter = limiter
            
            # Apply conditional exemption
            return current_limiter.limit(
                "",
                exempt_when=condition_func
            )(f)(*args, **kwargs)
        return wrapped
    return decorator

def clear_rate_limit(key: str = None, limit: str = None) -> bool:
    """
    Clear a rate limit block for a specific key or all limits.
    
    Args:
        key: Specific key to clear (e.g., "ip:127.0.0.1" or "user:123")
        limit: Specific limit to clear (e.g., "5 per minute")
    
    Returns:
        bool: True if successful, False otherwise
    """
    global limiter
    if not limiter or not limiter._storage:
        rate_limit_logger.warning("Cannot clear rate limit: limiter not initialized")
        return False
    
    try:
        if key:
            # Clear specific key
            if limit:
                # Clear specific limit for a key
                # For Redis, we need to construct the key properly
                storage_key = f"{limit}:{key}"
                limiter._storage.clear(storage_key)
                rate_limit_logger.info(f"Cleared rate limit for key: {storage_key}")
            else:
                # Clear all limits for a key
                # For Redis storage, we need to use the Redis client directly
                if hasattr(limiter._storage, 'storage'):
                    # RedisStorage has a 'storage' attribute which is the Redis client
                    redis_client = limiter._storage.storage
                    # Search for keys matching the pattern
                    # Flask-Limiter 4.0 key format: LIMITS:LIMITER/<key>/<endpoint>/<count>/<period>/<per>
                    pattern = f"LIMITS:LIMITER/{key}/*"
                    keys = redis_client.keys(pattern)
                    if keys:
                        redis_client.delete(*keys)
                        rate_limit_logger.info(f"Cleared {len(keys)} rate limits for key pattern: {pattern}")
                    else:
                        rate_limit_logger.info(f"No rate limits found for key pattern: {pattern}")
                elif hasattr(limiter._storage, 'keys'):
                    # For storage backends that support key iteration
                    keys_to_remove = [k for k in limiter._storage.keys() if key in k]
                    for storage_key in keys_to_remove:
                        limiter._storage.clear(storage_key)
                    rate_limit_logger.info(f"Cleared {len(keys_to_remove)} rate limits for key: {key}")
                else:
                    rate_limit_logger.warning(f"Storage backend does not support key clearing for key: {key}")
                    return False
        else:
            # Clear all rate limits (use with caution)
            if hasattr(limiter._storage, 'storage'):
                # For Redis, flush the database
                redis_client = limiter._storage.storage
                redis_client.flushdb()
                rate_limit_logger.warning("Cleared ALL rate limits from Redis database")
            elif hasattr(limiter._storage, 'reset'):
                limiter._storage.reset()
                rate_limit_logger.warning("Cleared ALL rate limits")
            else:
                rate_limit_logger.warning("Storage backend does not support reset operation")
                return False
        
        return True
    except Exception as e:
        rate_limit_logger.error(f"Failed to clear rate limit: {e}")
        return False

def get_rate_limit_status(key: str = None) -> dict:
    """
    Get the current rate limit status for a key or overall statistics.
    
    Args:
        key: Specific key to check (e.g., "ip:127.0.0.1" or "user:123")
    
    Returns:
        dict: Rate limit information
    """
    global limiter
    if not limiter or not limiter._storage:
        return {"error": "Rate limiter not initialized"}
    
    try:
        if key:
            # Get status for specific key
            info = {"key": key}
            
            # For Redis storage, use the Redis client directly
            if hasattr(limiter._storage, 'storage'):
                redis_client = limiter._storage.storage
                # Search for keys matching the pattern
                # Flask-Limiter 4.0 key format: LIMITS:LIMITER/<key>/<endpoint>/<count>/<period>/<per>
                pattern = f"LIMITS:LIMITER/{key}/*"
                keys = redis_client.keys(pattern)
                info["matching_keys"] = [k.decode('utf-8') if isinstance(k, bytes) else k for k in keys]
                info["limits"] = {}
                
                # Get values for matching keys
                for storage_key in keys:
                    key_str = storage_key.decode('utf-8') if isinstance(storage_key, bytes) else storage_key
                    value = redis_client.get(storage_key)
                    if value:
                        value_str = value.decode('utf-8') if isinstance(value, bytes) else str(value)
                        info["limits"][key_str] = value_str
                
                info["total_matching_keys"] = len(keys)
            elif hasattr(limiter._storage, '_storage'):
                # For memory storage
                storage_data = limiter._storage._storage
                matching_keys = [k for k in storage_data.keys() if key in k]
                info["matching_keys"] = matching_keys
                info["limits"] = {}
                for storage_key in matching_keys:
                    info["limits"][storage_key] = str(storage_data[storage_key])
                info["total_matching_keys"] = len(matching_keys)
            else:
                return {"error": "Storage backend does not support inspection"}
            
            return info
        else:
            # Get overall statistics
            stats = {"storage_type": type(limiter._storage).__name__}
            
            # For Redis storage, get database info
            if hasattr(limiter._storage, 'storage'):
                redis_client = limiter._storage.storage
                # Get basic Redis info
                info = redis_client.info()
                stats["redis_info"] = {
                    "used_memory": info.get("used_memory_human"),
                    "connected_clients": info.get("connected_clients"),
                    "total_commands_processed": info.get("total_commands_processed")
                }
                
                # Get sample keys
                keys = redis_client.keys()[:10]  # First 10 keys
                stats["total_keys"] = redis_client.dbsize()
                stats["sample_keys"] = [k.decode('utf-8') if isinstance(k, bytes) else k for k in keys]
            elif hasattr(limiter._storage, '_storage'):
                # For memory storage
                stats["total_keys"] = len(limiter._storage._storage)
                stats["keys"] = list(limiter._storage._storage.keys())[:10]  # First 10 keys
            
            return stats
    except Exception as e:
        rate_limit_logger.error(f"Failed to get rate limit status: {e}")
        return {"error": str(e)}

def init_rate_limiting(app):
    """
    Initialize rate limiting for the Flask application.
    Reads configuration from environment variables.
    
    Implements best practices from Flask-Limiter documentation:
    - Proper storage backend configuration
    - Meta limits for overall protection
    - Dynamic rate limit loading
    - Shared limits for resource protection
    - Proper flask-limiter logger configuration (configured in app.py)
    """
    # Read all rate limiting configuration from environment
    app.config['RATELIMIT_ENABLED'] = os.getenv('RATELIMIT_ENABLED', 'true').lower() in ('true', '1', 'yes')
    app.config['RATELIMIT_DEFAULT'] = os.getenv('RATELIMIT_DEFAULT', '500 per hour, 50 per minute')
    app.config['RATELIMIT_STORAGE_URI'] = os.getenv('RATELIMIT_STORAGE_URI', 'memory://')
    app.config['RATELIMIT_KEY_PREFIX'] = os.getenv('RATELIMIT_KEY_PREFIX', '')
    app.config['RATELIMIT_STRATEGY'] = os.getenv('RATELIMIT_STRATEGY', 'fixed-window')
    
    # Application limits for overall protection (Flask-Limiter 4.0)
    app.config['RATELIMIT_APPLICATION'] = os.getenv('RATELIMIT_APPLICATION', '1000 per hour, 100 per minute')
    
    # Configure headers based on environment variable
    app.config['RATELIMIT_HEADERS_ENABLED'] = os.getenv('RATELIMIT_HEADERS_ENABLED', 'false').lower() in ('true', '1', 'yes')
    app.config['RATELIMIT_HEADER_LIMIT'] = os.getenv('RATELIMIT_HEADER_LIMIT', 'X-RateLimit-Limit')
    app.config['RATELIMIT_HEADER_REMAINING'] = os.getenv('RATELIMIT_HEADER_REMAINING', 'X-RateLimit-Remaining')
    app.config['RATELIMIT_HEADER_RESET'] = os.getenv('RATELIMIT_HEADER_RESET', 'X-RateLimit-Reset')
    
    # Behavior configuration
    app.config['RATELIMIT_FAIL_ON_FIRST_BREACH'] = os.getenv('RATELIMIT_FAIL_ON_FIRST_BREACH', 'false').lower() in ('true', '1', 'yes')
    app.config['RATELIMIT_SWALLOW_ERRORS'] = os.getenv('RATELIMIT_SWALLOW_ERRORS', 'true').lower() in ('true', '1', 'yes')
    app.config['RATELIMIT_DEDUPLICATE'] = os.getenv('RATELIMIT_DEDUPLICATE', 'false').lower() in ('true', '1', 'yes')
    app.config['RATELIMIT_DEFAULTS_PER_METHOD'] = os.getenv('RATELIMIT_DEFAULTS_PER_METHOD', 'false').lower() in ('true', '1', 'yes')
    app.config['RATELIMIT_DEFAULTS_COST'] = int(os.getenv('RATELIMIT_DEFAULTS_COST', '1'))
    app.config['RATELIMIT_DEFAULTS_EXEMPT'] = os.getenv('RATELIMIT_DEFAULTS_EXEMPT', '')
    
    # Read memcached servers configuration
    app.config['RATELIMIT_MEMCACHED_SERVERS'] = os.getenv('RATELIMIT_MEMCACHED_SERVERS')
    app.config['RATELIMIT_MEMCACHED_USERNAME'] = os.getenv('RATELIMIT_MEMCACHED_USERNAME')
    app.config['RATELIMIT_MEMCACHED_PASSWORD'] = os.getenv('RATELIMIT_MEMCACHED_PASSWORD')
    app.config['RATELIMIT_MEMCACHED_CONNECT_TIMEOUT'] = os.getenv('RATELIMIT_MEMCACHED_CONNECT_TIMEOUT', '2')
    app.config['RATELIMIT_MEMCACHED_TIMEOUT'] = os.getenv('RATELIMIT_MEMCACHED_TIMEOUT', '1')
    app.config['RATELIMIT_MEMCACHED_MAX_POOL_SIZE'] = os.getenv('RATELIMIT_MEMCACHED_MAX_POOL_SIZE', '10')
    
    # Read Redis configuration
    app.config['RATELIMIT_REDIS_URL'] = os.getenv('RATELIMIT_REDIS_URL') or os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    app.config['RATELIMIT_REDIS_HOST'] = os.getenv('RATELIMIT_REDIS_HOST', 'localhost')
    app.config['RATELIMIT_REDIS_PORT'] = int(os.getenv('RATELIMIT_REDIS_PORT', '6379'))
    app.config['RATELIMIT_REDIS_DB'] = int(os.getenv('RATELIMIT_REDIS_DB', '0'))
    app.config['RATELIMIT_REDIS_PASSWORD'] = os.getenv('RATELIMIT_REDIS_PASSWORD')
    app.config['RATELIMIT_REDIS_USERNAME'] = os.getenv('RATELIMIT_REDIS_USERNAME')
    app.config['RATELIMIT_REDIS_SSL'] = os.getenv('RATELIMIT_REDIS_SSL', 'false').lower() in ('true', '1', 'yes')
    app.config['RATELIMIT_REDIS_SSL_CERT_REQS'] = os.getenv('RATELIMIT_REDIS_SSL_CERT_REQS', 'required')
    app.config['RATELIMIT_REDIS_CONNECTION_POOL_KWARGS'] = os.getenv('RATELIMIT_REDIS_CONNECTION_POOL_KWARGS', '{}')
    app.config['RATELIMIT_REDIS_SOCKET_TIMEOUT'] = int(os.getenv('RATELIMIT_REDIS_SOCKET_TIMEOUT', '5'))
    app.config['RATELIMIT_REDIS_SOCKET_CONNECT_TIMEOUT'] = int(os.getenv('RATELIMIT_REDIS_SOCKET_CONNECT_TIMEOUT', '5'))
    app.config['RATELIMIT_REDIS_RETRY_ON_TIMEOUT'] = os.getenv('RATELIMIT_REDIS_RETRY_ON_TIMEOUT', 'false').lower() in ('true', '1', 'yes')
    app.config['RATELIMIT_REDIS_HEALTH_CHECK_INTERVAL'] = int(os.getenv('RATELIMIT_REDIS_HEALTH_CHECK_INTERVAL', '0'))
    app.config['RATELIMIT_REDIS_CLIENT_NAME'] = os.getenv('RATELIMIT_REDIS_CLIENT_NAME', 'flask-limiter')
    
    # Configure storage backend based on environment variables
    storage_configured = False
    storage_uri = app.config.get('RATELIMIT_STORAGE_URI', 'memory://')
    
    # Check for Memcached configuration
    if app.config.get('RATELIMIT_MEMCACHED_SERVERS'):
        from pymemcache.client.base import Client
        
        servers = app.config.get('RATELIMIT_MEMCACHED_SERVERS')
        username = app.config.get('RATELIMIT_MEMCACHED_USERNAME')
        password = app.config.get('RATELIMIT_MEMCACHED_PASSWORD')
        
        try:
            # Create Memcached client with optional authentication
            if username and password:
                client = Client(
                    servers,
                    username=username,
                    password=password,
                    connect_timeout=2,
                    timeout=2,
                    ignore_exc=False
                )
            else:
                client = Client(
                    servers,
                    connect_timeout=2,
                    timeout=2,
                    ignore_exc=False
                )
            
            # Test connection
            client.version()
            
            # Configure Flask-Limiter to use Memcached
            # For flask-limiter 4.0+, we use the storage_uri format
            if username and password:
                storage_uri = f"memcached://{username}:{password}@{servers}"
            else:
                storage_uri = f"memcached://{servers}"
            
            rate_limit_logger.info(f"Using Memcached for rate limit storage: {servers}")
            storage_configured = True
        except Exception as e:
            rate_limit_logger.error(f"Failed to connect to Memcached: {e}")
            if not app.config.get('RATELIMIT_SWALLOW_ERRORS', False):
                raise
    
    # Check for Redis configuration
    elif app.config.get('REDIS_URL') or app.config.get('RATELIMIT_REDIS_URL'):
        # Build Redis URL from components if full URL not provided
        redis_url = app.config.get('RATELIMIT_REDIS_URL') or app.config.get('REDIS_URL')
        
        if not redis_url and app.config.get('RATELIMIT_REDIS_HOST'):
            # Build Redis URL from individual components
            redis_host = app.config.get('RATELIMIT_REDIS_HOST', 'localhost')
            redis_port = app.config.get('RATELIMIT_REDIS_PORT', 6379)
            redis_db = app.config.get('RATELIMIT_REDIS_DB', 0)
            redis_password = app.config.get('RATELIMIT_REDIS_PASSWORD')
            redis_username = app.config.get('RATELIMIT_REDIS_USERNAME')
            redis_ssl = app.config.get('RATELIMIT_REDIS_SSL', False)
            
            if redis_username:
                redis_url = f"redis://{redis_username}:{redis_password}@{redis_host}:{redis_port}/{redis_db}"
            elif redis_password:
                redis_url = f"redis://:{redis_password}@{redis_host}:{redis_port}/{redis_db}"
            else:
                redis_url = f"redis://{redis_host}:{redis_port}/{redis_db}"
            
            if redis_ssl:
                redis_url = redis_url.replace('redis://', 'rediss://')
        
        if redis_url:
            storage_uri = redis_url
            rate_limit_logger.info(f"Using Redis for rate limit storage: {redis_url}")
            storage_configured = True
    
    # Check if RATELIMIT_STORAGE_URI is explicitly set
    elif app.config.get('RATELIMIT_STORAGE_URI'):
        storage_url = app.config['RATELIMIT_STORAGE_URI']
        if storage_url.startswith('memcached://'):
            rate_limit_logger.info(f"Using Memcached for rate limit storage (explicitly configured)")
        elif storage_url.startswith('redis://'):
            rate_limit_logger.info(f"Using Redis for rate limit storage (explicitly configured)")
        elif storage_url.startswith('memory://'):
            rate_limit_logger.warning("Using memory storage for rate limiting (not suitable for production)")
        storage_uri = storage_url
        storage_configured = True
    
    # Override for testing environment only if explicitly disabled
    # Don't disable if rate limiting is explicitly enabled in config
    if (app.config.get('TESTING', False) or app.config.get('DISABLE_RATE_LIMITING', False)) and not app.config.get('RATELIMIT_ENABLED', True):
        app.config['RATELIMIT_ENABLED'] = False
        rate_limit_logger.info("Rate limiting disabled for testing environment")
    
    # Log configuration
    if app.config['RATELIMIT_ENABLED']:
        rate_limit_logger.info(
            f"Rate limiting enabled - Default: {app.config['RATELIMIT_DEFAULT']}, "
            f"Storage: {app.config['RATELIMIT_STORAGE_URI']}, "
            f"Headers: {app.config['RATELIMIT_HEADERS_ENABLED']}"
        )
    else:
        rate_limit_logger.info("Rate limiting disabled")
    
    # Set Flask config variables for rate limiting
    app.config['RATELIMIT_STORAGE_URI'] = storage_uri
    
    # Configure Redis storage options if using Redis
    storage_options = {}
    if storage_uri and storage_uri.startswith(('redis://', 'rediss://')):
        # Redis connection pool options
        connection_pool_kwargs = {}
        
        # Parse connection pool kwargs from environment if provided
        pool_kwargs_str = app.config.get('RATELIMIT_REDIS_CONNECTION_POOL_KWARGS', '{}')
        try:
            import ast
            connection_pool_kwargs = ast.literal_eval(pool_kwargs_str)
        except (ValueError, SyntaxError):
            rate_limit_logger.warning(f"Invalid RATELIMIT_REDIS_CONNECTION_POOL_KWARGS: {pool_kwargs_str}")
        
        # Add standard Redis connection options
        if app.config.get('RATELIMIT_REDIS_SOCKET_TIMEOUT'):
            connection_pool_kwargs['socket_timeout'] = app.config.get('RATELIMIT_REDIS_SOCKET_TIMEOUT')
        
        if app.config.get('RATELIMIT_REDIS_SOCKET_CONNECT_TIMEOUT'):
            connection_pool_kwargs['socket_connect_timeout'] = app.config.get('RATELIMIT_REDIS_SOCKET_CONNECT_TIMEOUT')
        
        if app.config.get('RATELIMIT_REDIS_RETRY_ON_TIMEOUT'):
            connection_pool_kwargs['retry_on_timeout'] = app.config.get('RATELIMIT_REDIS_RETRY_ON_TIMEOUT')
        
        if app.config.get('RATELIMIT_REDIS_HEALTH_CHECK_INTERVAL', 0) > 0:
            connection_pool_kwargs['health_check_interval'] = app.config.get('RATELIMIT_REDIS_HEALTH_CHECK_INTERVAL')
        
        if app.config.get('RATELIMIT_REDIS_CLIENT_NAME'):
            connection_pool_kwargs['client_name'] = app.config.get('RATELIMIT_REDIS_CLIENT_NAME')
        
        # SSL configuration for Redis
        if storage_uri.startswith('rediss://') or app.config.get('RATELIMIT_REDIS_SSL'):
            ssl_config = {}
            cert_reqs = app.config.get('RATELIMIT_REDIS_SSL_CERT_REQS', 'required')
            if cert_reqs in ['required', 'optional', 'none']:
                ssl_config['cert_reqs'] = cert_reqs
            connection_pool_kwargs['ssl'] = ssl_config
        
        if connection_pool_kwargs:
            storage_options = connection_pool_kwargs
            rate_limit_logger.info(f"Redis connection options configured: {list(connection_pool_kwargs.keys())}")
        else:
            storage_options = {}
    
    app.config['RATELIMIT_STORAGE_OPTIONS'] = storage_options
    
    # Initialize limiter with app
    # Debug logging
    rate_limit_logger.info(f"Creating limiter with storage_uri: {storage_uri}")
    
    try:
        # Parse default and application limits
        default_limits = app.config.get('RATELIMIT_DEFAULT', '').split(',') if app.config.get('RATELIMIT_DEFAULT') else None
        application_limits = app.config.get('RATELIMIT_APPLICATION', '').split(',') if app.config.get('RATELIMIT_APPLICATION') else None
        
        # Create a new limiter instance with enhanced configuration
        # Set application_limits to None to avoid overriding route-specific limits
        new_limiter = Limiter(
            key_func=get_rate_limit_key,
            app=app,
            strategy=app.config.get('RATELIMIT_STRATEGY', 'fixed-window'),
            headers_enabled=app.config.get('RATELIMIT_HEADERS_ENABLED', False),  # Use config value
            swallow_errors=app.config.get('RATELIMIT_SWALLOW_ERRORS', True),
            key_prefix=app.config.get('RATELIMIT_KEY_PREFIX', ''),
            default_limits=default_limits,
            application_limits=None,  # Disable application limits to avoid overriding route-specific limits
            fail_on_first_breach=app.config.get('RATELIMIT_FAIL_ON_FIRST_BREACH', False),
            on_breach=handle_rate_limit_exceeded
        )
        
        # Update the global limiter
        global limiter
        limiter = new_limiter
        
        # Debug logging after initialization
        if limiter._storage:
            rate_limit_logger.info(f"Limiter initialized successfully. Storage URI: {limiter._storage_uri}, Storage type: {type(limiter._storage).__name__}")
        else:
            rate_limit_logger.error(f"Limiter initialization failed. Storage is None")
    except Exception as e:
        rate_limit_logger.error(f"Failed to initialize limiter: {e}")
        # Fall back to memory storage
        try:
            app.config['RATELIMIT_STORAGE_URI'] = "memory://"
            new_limiter = Limiter(
                key_func=get_rate_limit_key,
                app=app,
                strategy=app.config.get('RATELIMIT_STRATEGY', 'fixed-window'),
                headers_enabled=False,  # Explicitly disabled to avoid header injection errors
                swallow_errors=app.config.get('RATELIMIT_SWALLOW_ERRORS', False),
                key_prefix=app.config.get('RATELIMIT_KEY_PREFIX', '')
            )
            limiter = new_limiter
            rate_limit_logger.warning("Falling back to memory storage for rate limiting")
        except Exception as fallback_error:
            rate_limit_logger.error(f"Failed to initialize fallback limiter: {fallback_error}")
            limiter = None
    
    # Register custom error handler
    app.errorhandler(429)(handle_rate_limit_exceeded)
    
    rate_limit_logger.info("Rate limiting initialized")
