"""
CSRF protection utilities for non-authenticated routes.
Provides additional CSRF protection for API endpoints and form submissions.
"""

import logging
import hmac
import hashlib
import time
from typing import Callable, Optional
from flask import request, session, current_app, jsonify, abort
from functools import wraps
from urllib.parse import urlparse

# Configure logger
csrf_logger = logging.getLogger("csrf")

class CSRFTokenManager:
    """
    Manages CSRF tokens for non-authenticated routes.
    """
    
    @staticmethod
    def generate_token(secret_key: str, timestamp: Optional[int] = None) -> str:
        """Generate a CSRF token."""
        if timestamp is None:
            timestamp = int(time.time())
        
        # Create token using HMAC with timestamp
        message = f"{timestamp}:{request.remote_addr or 'unknown'}"
        token = hmac.new(
            secret_key.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        return f"{timestamp}:{token}"
    
    @staticmethod
    def validate_token(token: str, secret_key: str, max_age: int = 3600) -> bool:
        """Validate a CSRF token."""
        try:
            timestamp_str, hash_str = token.split(':', 1)
            timestamp = int(timestamp_str)
            
            # Check token age
            if time.time() - timestamp > max_age:
                csrf_logger.warning(f"CSRF token expired - Age: {time.time() - timestamp}s")
                return False
            
            # Recreate expected token
            expected_message = f"{timestamp}:{request.remote_addr or 'unknown'}"
            expected_hash = hmac.new(
                secret_key.encode('utf-8'),
                expected_message.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            # Compare hashes
            is_valid = hmac.compare_digest(hash_str, expected_hash)
            
            if not is_valid:
                csrf_logger.warning("CSRF token validation failed - Hash mismatch")
            
            return is_valid
            
        except Exception as e:
            csrf_logger.error(f"CSRF token validation error: {str(e)}")
            return False
    
    @staticmethod
    def get_token_from_request() -> Optional[str]:
        """Extract CSRF token from request."""
        # Check header first
        token = request.headers.get('X-CSRF-Token')
        if token:
            return token
        
        # Check form data
        if request.form:
            token = request.form.get('csrf_token')
            if token:
                return token
        
        # Check JSON data
        if request.is_json:
            data = request.get_json(silent=True)
            if data and isinstance(data, dict):
                token = data.get('csrf_token')
                if token:
                    return token
        
        return None


def csrf_protect_for_anonymous(max_age: int = 3600) -> Callable:
    """
    CSRF protection decorator for non-authenticated routes.
    
    Args:
        max_age: Maximum age of CSRF token in seconds (default: 1 hour)
    """
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def wrapped(*args, **kwargs):
            # Skip CSRF protection for GET requests
            if request.method in ['GET', 'HEAD', 'OPTIONS']:
                return f(*args, **kwargs)
            
            # Get secret key
            secret_key = current_app.config.get('SECRET_KEY')
            if not secret_key:
                csrf_logger.error("CSRF protection failed: No secret key configured")
                abort(500, description="Server configuration error")
            
            # Get token from request
            token = CSRFTokenManager.get_token_from_request()
            if not token:
                client_ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
                client_ip = client_ip or request.remote_addr or "-"
                
                csrf_logger.warning(
                    f"CSRF token missing - IP: {client_ip}, "
                    f"Path: {request.path}, Method: {request.method}"
                )
                
                if request.path.startswith("/api/") or request.headers.get("Accept") == "application/json":
                    return jsonify({"error": "CSRF token required"}), 403
                
                abort(403, description="CSRF token required")
            
            # Validate token
            if not CSRFTokenManager.validate_token(token, secret_key, max_age):
                client_ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
                client_ip = client_ip or request.remote_addr or "-"
                
                csrf_logger.warning(
                    f"CSRF token invalid - IP: {client_ip}, "
                    f"Path: {request.path}, Method: {request.method}"
                )
                
                if request.path.startswith("/api/") or request.headers.get("Accept") == "application/json":
                    return jsonify({"error": "Invalid CSRF token"}), 403
                
                abort(403, description="Invalid CSRF token")
            
            return f(*args, **kwargs)
        
        return wrapped
    return decorator


def generate_csrf_token_for_anonymous() -> str:
    """
    Generate a CSRF token for the current session.
    """
    secret_key = current_app.config.get('SECRET_KEY')
    if not secret_key:
        raise RuntimeError("No secret key configured")
    
    return CSRFTokenManager.generate_token(secret_key)


def add_csrf_token_to_response(response):
    """
    Add CSRF token to response for non-authenticated routes.
    This can be used in after_request handlers.
    """
    # Only add token for HTML responses
    content_type = response.headers.get('Content-Type', '')
    if 'text/html' not in content_type:
        return response
    
    # Check if user is not authenticated
    from flask_login import current_user
    if current_user.is_authenticated:
        return response
    
    # Generate token
    try:
        token = generate_csrf_token_for_anonymous()
        # Add token as a cookie
        response.set_cookie(
            'csrf_token',
            token,
            max_age=3600,  # 1 hour
            httponly=False,  # Allow JavaScript access
            secure=request.is_secure,
            samesite='Strict'
        )
    except Exception as e:
        csrf_logger.error(f"Failed to add CSRF token to response: {str(e)}")
    
    return response


def validate_origin_for_api() -> Callable:
    """
    Validate Origin/Referer headers for API endpoints.
    Provides additional protection against CSRF attacks.
    """
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def wrapped(*args, **kwargs):
            # Only apply to state-changing methods
            if request.method not in ['POST', 'PUT', 'DELETE', 'PATCH']:
                return f(*args, **kwargs)
            
            # Get origin and referer
            origin = request.headers.get('Origin')
            referer = request.headers.get('Referer')
            
            # Get server base URL
            server_name = current_app.config.get('SERVER_NAME', request.host)
            if not server_name:
                # Fallback to request host
                server_name = request.host
            
            # Validate origin
            if origin:
                try:
                    origin_host = urlparse(origin).netloc
                    if origin_host != server_name:
                        csrf_logger.warning(
                            f"Invalid Origin header - Origin: {origin}, "
                            f"Expected: {server_name}, IP: {request.remote_addr}"
                        )
                        abort(403, description="Invalid origin")
                except Exception as e:
                    csrf_logger.error(f"Origin validation error: {str(e)}")
                    abort(403, description="Invalid origin")
            
            # Validate referer if no origin
            elif referer:
                try:
                    referer_host = urlparse(referer).netloc
                    if referer_host != server_name:
                        csrf_logger.warning(
                            f"Invalid Referer header - Referer: {referer}, "
                            f"Expected: {server_name}, IP: {request.remote_addr}"
                        )
                        abort(403, description="Invalid referer")
                except Exception as e:
                    csrf_logger.error(f"Referer validation error: {str(e)}")
                    abort(403, description="Invalid referer")
            
            # Log successful validation for debugging
            csrf_logger.debug(f"Origin/Referer validated for {request.path}")
            
            return f(*args, **kwargs)
        
        return wrapped
    return decorator