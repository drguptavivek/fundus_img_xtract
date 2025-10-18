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

# Initialize limiter (will be configured in init_rate_limiting)
limiter = Limiter(
    key_func=get_rate_limit_key,
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
    Reads configuration from environment variables.
    """
    # Read all rate limiting configuration from environment
    app.config['RATELIMIT_ENABLED'] = app.config.get('RATELIMIT_ENABLED', 'true').lower() in ('true', '1', 'yes')
    app.config['RATELIMIT_DEFAULT'] = app.config.get('RATELIMIT_DEFAULT', '500 per hour, 50 per minute')
    app.config['RATELIMIT_STORAGE_URL'] = app.config.get('RATELIMIT_STORAGE_URL', 'memory://')
    app.config['RATELIMIT_KEY_PREFIX'] = app.config.get('RATELIMIT_KEY_PREFIX', '')
    app.config['RATELIMIT_STRATEGY'] = app.config.get('RATELIMIT_STRATEGY', 'fixed-window')
    app.config['RATELIMIT_HEADERS_ENABLED'] = app.config.get('RATELIMIT_HEADERS_ENABLED', 'true').lower() in ('true', '1', 'yes')
    app.config['RATELIMIT_HEADER_RESET'] = app.config.get('RATELIMIT_HEADER_RESET', 'false').lower() in ('true', '1', 'yes')
    app.config['RATELIMIT_HEADER_REMAINING'] = app.config.get('RATELIMIT_HEADER_REMAINING', 'true').lower() in ('true', '1', 'yes')
    app.config['RATELIMIT_FAIL_ON_FIRST_BREACH'] = app.config.get('RATELIMIT_FAIL_ON_FIRST_BREACH', 'false').lower() in ('true', '1', 'yes')
    app.config['RATELIMIT_SWALLOW_ERRORS'] = app.config.get('RATELIMIT_SWALLOW_ERRORS', 'false').lower() in ('true', '1', 'yes')
    app.config['RATELIMIT_DEDUPLICATE'] = app.config.get('RATELIMIT_DEDUPLICATE', 'false').lower() in ('true', '1', 'yes')
    app.config['RATELIMIT_DEFAULTS_PER_METHOD'] = app.config.get('RATELIMIT_DEFAULTS_PER_METHOD', 'false').lower() in ('true', '1', 'yes')
    app.config['RATELIMIT_DEFAULTS_COST'] = int(app.config.get('RATELIMIT_DEFAULTS_COST', '1'))
    app.config['RATELIMIT_DEFAULTS_EXEMPT'] = app.config.get('RATELIMIT_DEFAULTS_EXEMPT', '')
    
    # Configure storage backend based on environment variables
    storage_configured = False
    
    # Check for Memcached configuration (new method)
    if app.config.get('RATELIMIT_MEMCACHED_SERVERS'):
        from pymemcache.client.base import Client
        from pymemcache.client.rendezvous import RendezvousHash
        from flask_limiter.util import MemcachedStorage
        
        servers = app.config.get('RATELIMIT_MEMCACHED_SERVERS').split(',')
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
            app.config['RATELIMIT_STORAGE_URL'] = f"memcached://{','.join(servers)}"
            rate_limit_logger.info(f"Using Memcached for rate limit storage: {servers}")
            storage_configured = True
        except Exception as e:
            rate_limit_logger.error(f"Failed to connect to Memcached: {e}")
            if not app.config.get('RATELIMIT_SWALLOW_ERRORS', False):
                raise
    
    # Check for Redis configuration
    elif app.config.get('REDIS_URL'):
        app.config['RATELIMIT_STORAGE_URL'] = app.config['REDIS_URL']
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
    
    # Initialize limiter with app
    limiter.init_app(app)
    
    # Register custom error handler
    app.errorhandler(429)(handle_rate_limit_exceeded)
    
    rate_limit_logger.info("Rate limiting initialized")