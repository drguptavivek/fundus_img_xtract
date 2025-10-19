"""
Rate limiting utilities for the Flask application.
Provides different rate limiting strategies for various endpoints.
"""

import os
import logging
from functools import wraps
from typing import Callable, Optional

from flask import request, jsonify, current_app, g
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from sqlalchemy import text
from models import Session

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
            
            # Apply rate limit using Flask-Limiter directly
            return limiter.limit(
                limit,
                per_method=per_method,
                methods=methods,
                error_message=error_message or f"Rate limit exceeded: {limit}"
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
            # Get the current limiter instance at runtime
            from flask import current_app
            current_limiter = current_app.extensions.get('limiter')
            if not current_limiter:
                current_limiter = limiter
            
            # Apply rate limit using Flask-Limiter directly
            return current_limiter.limit(
                limit,
                per_method=per_method,
                methods=methods,
                error_message=error_message or f"Rate limit exceeded: {limit}"
            )(f)(*args, **kwargs)
        
        return wrapped
    
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
    
    # Also log to runtime_error for security monitoring
    runtime_logger = logging.getLogger("runtime_error")
    runtime_logger.warning(
        f"Rate limit violation - IP: {client_ip}, User: {user_info}, "
        f"Endpoint: {endpoint}, Path: {path}, Method: {method}, "
        f"Limit: {limit}"
    )

# Custom error handler for rate limit exceeded
def handle_rate_limit_exceeded(e):
    """
    Custom error handler for rate limit exceeded.
    Returns JSON response for API endpoints and HTML for others.
    """
    # Extract limit information from the exception
    limit = getattr(e, 'limit', 'unknown')
    limit_key = getattr(e, 'key', 'unknown')
    
    # Log the violation
    log_rate_limit_violation(limit_key, limit)
    
    # Get retry after value
    retry_after = getattr(e, 'retry_after', 60)
    
    # Add flash message with rate limit information
    from flask import flash
    flash(f"Rate limit exceeded. Please try again in {retry_after} seconds.", "warning")
    
    # Check if this is an API request
    if request.path.startswith('/api/') or request.headers.get('Accept') == 'application/json':
        return jsonify({
            "error": "Rate limit exceeded",
            "message": str(e.description),
            "retry_after": retry_after
        }), 429
    
    # Return HTML error page for regular requests
    from flask import render_template, redirect, url_for
    # For login page, redirect back to login with the flash message
    if request.path == '/login':
        return redirect(url_for('auth.login'))
    
    return render_template(
        "errors/429.html",
        error_message=str(e.description),
        retry_after=retry_after
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
    Reads configuration from environment variables.
    """
    # Read all rate limiting configuration from environment
    app.config['RATELIMIT_ENABLED'] = os.getenv('RATELIMIT_ENABLED', 'true').lower() in ('true', '1', 'yes')
    app.config['RATELIMIT_DEFAULT'] = os.getenv('RATELIMIT_DEFAULT', '500 per hour, 50 per minute')
    app.config['RATELIMIT_STORAGE_URL'] = os.getenv('RATELIMIT_STORAGE_URL', 'memory://')
    app.config['RATELIMIT_KEY_PREFIX'] = os.getenv('RATELIMIT_KEY_PREFIX', '')
    app.config['RATELIMIT_STRATEGY'] = os.getenv('RATELIMIT_STRATEGY', 'fixed-window')
    # Configure headers based on environment variable
    headers_enabled = os.getenv('RATELIMIT_HEADERS_ENABLED', 'false').lower() in ('true', '1', 'yes')
    app.config['RATELIMIT_HEADERS_ENABLED'] = headers_enabled
    app.config['RATELIMIT_HEADER_RESET'] = os.getenv('RATELIMIT_HEADER_RESET', 'false').lower() in ('true', '1', 'yes')
    app.config['RATELIMIT_HEADER_REMAINING'] = os.getenv('RATELIMIT_HEADER_REMAINING', 'true').lower() in ('true', '1', 'yes')
    app.config['RATELIMIT_FAIL_ON_FIRST_BREACH'] = os.getenv('RATELIMIT_FAIL_ON_FIRST_BREACH', 'false').lower() in ('true', '1', 'yes')
    app.config['RATELIMIT_SWALLOW_ERRORS'] = os.getenv('RATELIMIT_SWALLOW_ERRORS', 'false').lower() in ('true', '1', 'yes')
    app.config['RATELIMIT_DEDUPLICATE'] = os.getenv('RATELIMIT_DEDUPLICATE', 'false').lower() in ('true', '1', 'yes')
    app.config['RATELIMIT_DEFAULTS_PER_METHOD'] = os.getenv('RATELIMIT_DEFAULTS_PER_METHOD', 'false').lower() in ('true', '1', 'yes')
    app.config['RATELIMIT_DEFAULTS_COST'] = int(os.getenv('RATELIMIT_DEFAULTS_COST', '1'))
    app.config['RATELIMIT_DEFAULTS_EXEMPT'] = os.getenv('RATELIMIT_DEFAULTS_EXEMPT', '')
    
    # Read memcached servers configuration
    app.config['RATELIMIT_MEMCACHED_SERVERS'] = os.getenv('RATELIMIT_MEMCACHED_SERVERS')
    app.config['RATELIMIT_MEMCACHED_USERNAME'] = os.getenv('RATELIMIT_MEMCACHED_USERNAME')
    app.config['RATELIMIT_MEMCACHED_PASSWORD'] = os.getenv('RATELIMIT_MEMCACHED_PASSWORD')
    
    # Configure storage backend based on environment variables
    storage_configured = False
    storage_uri = app.config.get('RATELIMIT_STORAGE_URL', 'memory://')
    
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
    elif app.config.get('REDIS_URL'):
        storage_uri = app.config['REDIS_URL']
        rate_limit_logger.info("Using Redis for rate limit storage")
        storage_configured = True
    
    # Check if RATELIMIT_STORAGE_URL is explicitly set
    elif app.config.get('RATELIMIT_STORAGE_URL'):
        storage_url = app.config['RATELIMIT_STORAGE_URL']
        if storage_url.startswith('memcached://'):
            rate_limit_logger.info(f"Using Memcached for rate limit storage (explicitly configured)")
        elif storage_url.startswith('redis://'):
            rate_limit_logger.info(f"Using Redis for rate limit storage (explicitly configured)")
        elif storage_url.startswith('memory://'):
            rate_limit_logger.warning("Using memory storage for rate limiting (not suitable for production)")
        storage_uri = storage_url
        storage_configured = True
    
    # Override for testing environment
    if app.config.get('TESTING', False) or app.config.get('DISABLE_RATE_LIMITING', False):
        app.config['RATELIMIT_ENABLED'] = False
        rate_limit_logger.info("Rate limiting disabled for testing environment")
    
    # Log configuration
    if app.config['RATELIMIT_ENABLED']:
        rate_limit_logger.info(
            f"Rate limiting enabled - Default: {app.config['RATELIMIT_DEFAULT']}, "
            f"Storage: {app.config['RATELIMIT_STORAGE_URL']}, "
            f"Headers: {app.config['RATELIMIT_HEADERS_ENABLED']}"
        )
    else:
        rate_limit_logger.info("Rate limiting disabled")
    
    # Set Flask config variables for rate limiting
    app.config['RATELIMIT_STORAGE_URI'] = storage_uri
    app.config['RATELIMIT_STORAGE_OPTIONS'] = {}
    
    # Initialize limiter with app
    global limiter
    
    # Debug logging
    rate_limit_logger.info(f"Creating limiter with storage_uri: {storage_uri}")
    
    try:
        # Create a new limiter instance - it will read from Flask config
        new_limiter = Limiter(
            key_func=get_rate_limit_key,
            app=app,
            strategy=app.config.get('RATELIMIT_STRATEGY', 'fixed-window'),
            headers_enabled=False,  # Disable headers to avoid compatibility issues
            swallow_errors=app.config.get('RATELIMIT_SWALLOW_ERRORS', False),
            key_prefix=app.config.get('RATELIMIT_KEY_PREFIX', '')
        )
        
        # Update the global limiter
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
                headers_enabled=False,
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