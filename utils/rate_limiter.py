"""
Rate limiting utilities for the Flask application.
Provides different rate limiting strategies for various endpoints.
"""

import logging
from functools import wraps
from typing import Callable, Optional

from flask import request, jsonify, current_app, g
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from sqlalchemy import text
from models import Session

# Configure logger
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

# Initialize limiter
limiter = Limiter(
    key_func=get_rate_limit_key,
    default_limits=["2000 per day", "500 per hour"],
    storage_uri="memory://",  # In production, use Redis or database storage
)

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
        # Apply rate limit using Flask-Limiter directly
        return limiter.limit(
            limit,
            per_method=per_method,
            methods=methods,
            error_message=error_message or f"Rate limit exceeded: {limit}"
        )(f)
    
    return decorator

def auth_rate_limit(limit: str = "5 per minute") -> Callable:
    """
    Specialized rate limit for authentication endpoints.
    More restrictive than general rate limits.
    """
    return rate_limit(
        limit=limit,
        per_method=True,
        methods=["POST"],
        error_message="Too many authentication attempts. Please try again later."
    )

def upload_rate_limit(limit: str = "10 per minute") -> Callable:
    """
    Rate limit for file upload endpoints.
    """
    return rate_limit(
        limit=limit,
        per_method=True,
        methods=["POST"],
        error_message="Upload rate limit exceeded. Please wait before uploading more files."
    )

def api_rate_limit(limit: str = "100 per minute") -> Callable:
    """
    Rate limit for general API endpoints.
    """
    return rate_limit(
        limit=limit,
        per_method=True,
        error_message="API rate limit exceeded. Please reduce your request frequency."
    )

def admin_rate_limit(limit: str = "50 per minute") -> Callable:
    """
    Rate limit for admin endpoints.
    """
    return rate_limit(
        limit=limit,
        per_method=True,
        error_message="Admin operation rate limit exceeded."
    )

def log_rate_limit_violation():
    """
    Log rate limit violations for security monitoring.
    """
    from flask_login import current_user
    
    client_ip = get_remote_address()
    endpoint = request.endpoint or "unknown"
    method = request.method
    
    user_info = "anonymous"
    if hasattr(current_user, 'is_authenticated') and current_user.is_authenticated:
        user_info = f"user:{current_user.id}({current_user.username})"
    
    rate_limit_logger.warning(
        f"Rate limit violation - IP: {client_ip}, User: {user_info}, "
        f"Endpoint: {endpoint}, Method: {method}"
    )

# Custom error handler for rate limit exceeded
def handle_rate_limit_exceeded(e):
    """
    Custom error handler for rate limit exceeded.
    Returns JSON response for API endpoints and HTML for others.
    """
    log_rate_limit_violation()
    
    # Check if this is an API request
    if request.path.startswith('/api/') or request.headers.get('Accept') == 'application/json':
        return jsonify({
            "error": "Rate limit exceeded",
            "message": str(e.description),
            "retry_after": getattr(e, 'retry_after', 60)
        }), 429
    
    # Return HTML error page for regular requests
    from flask import render_template
    return render_template(
        "errors/429.html",
        error_message=str(e.description),
        retry_after=getattr(e, 'retry_after', 60)
    ), 429

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
                "upload": "100 per minute",
                "api": "1000 per minute"
            }
        elif user.has_role('data_manager', 'ophthalmologist'):
            return {
                "default": "2000 per hour",
                "upload": "50 per minute",
                "api": "500 per minute"
            }
        elif user.has_role('fileUploader', 'optometrist'):
            return {
                "default": "1000 per hour",
                "upload": "20 per minute",
                "api": "200 per minute"
            }
        else:
            return {
                "default": "500 per hour",
                "upload": "10 per minute",
                "api": "100 per minute"
            }

def init_rate_limiting(app):
    """
    Initialize rate limiting for the Flask application.
    """
    # Configure rate limiting based on environment
    if app.config.get('TESTING', False):
        # Disable rate limiting in testing
        app.config['RATELIMIT_ENABLED'] = False
        rate_limit_logger.info("Rate limiting disabled for testing environment")
    elif app.config.get('DISABLE_RATE_LIMITING', False):
        # Explicitly disabled
        app.config['RATELIMIT_ENABLED'] = False
        rate_limit_logger.info("Rate limiting explicitly disabled")
    else:
        # Enable rate limiting
        app.config['RATELIMIT_ENABLED'] = True
        
        if app.config.get('DEBUG', False):
            # More lenient limits in development
            app.config['RATELIMIT_DEFAULT'] = "5000 per day, 1000 per hour"
            rate_limit_logger.info("Development rate limits applied")
        else:
            # Production limits
            app.config['RATELIMIT_DEFAULT'] = "2000 per day, 500 per hour"
            rate_limit_logger.info("Production rate limits applied")
        
        # Configure storage backend based on environment
        if app.config.get('REDIS_URL'):
            # Use Redis for distributed rate limiting
            app.config['RATELIMIT_STORAGE_URL'] = app.config['REDIS_URL']
            rate_limit_logger.info("Using Redis for rate limit storage")
        else:
            # Fall back to memory storage (not suitable for multi-process deployments)
            app.config['RATELIMIT_STORAGE_URL'] = "memory://"
            rate_limit_logger.warning("Using memory storage for rate limiting (not suitable for production)")
    
    # Initialize limiter with app
    limiter.init_app(app)
    
    # Register custom error handler
    app.errorhandler(429)(handle_rate_limit_exceeded)
    
    rate_limit_logger.info("Rate limiting initialized")