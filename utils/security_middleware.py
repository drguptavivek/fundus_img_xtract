"""
Security middleware for protecting against large or malformed payload attacks.
Provides additional protection layers for non-authenticated routes.
"""

import logging
from typing import Callable, Optional
from flask import request, jsonify, current_app, g, abort, Response
from functools import wraps
import json
from werkzeug.exceptions import RequestEntityTooLarge

# Configure logger
security_logger = logging.getLogger("security")

class PayloadSizeValidator:
    """
    Middleware to validate request payload size and structure.
    """
    
    def __init__(self, app=None):
        self.app = app
        if app is not None:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize the middleware with Flask app."""
        app.before_request(self._validate_request)
        
        # Register error handlers
        app.errorhandler(RequestEntityTooLarge)(self._handle_payload_too_large)
        app.errorhandler(json.JSONDecodeError)(self._handle_malformed_json)
    
    def _validate_request(self):
        """Validate incoming request before processing."""
        # Skip validation for static files and health checks
        if self._should_skip_validation():
            return
        
        # Get client IP for logging
        client_ip = self._get_client_ip()
        
        # Check content length against stricter limits for non-authenticated routes
        if not self._is_authenticated_route() and self._is_payload_sensitive():
            content_length = request.content_length or 0
            
            # Stricter limits for non-authenticated routes
            max_size = self._get_max_payload_size()
            
            if content_length > max_size:
                security_logger.warning(
                    f"Payload size exceeded - IP: {client_ip}, "
                    f"Path: {request.path}, Size: {content_length}, Limit: {max_size}"
                )
                abort(413, description=f"Request entity too large. Maximum size is {max_size} bytes.")
        
        # Validate JSON structure for JSON endpoints
        if request.is_json and not self._is_authenticated_route():
            try:
                # This will raise JSONDecodeError if malformed
                request.get_json()
            except Exception as e:
                security_logger.warning(
                    f"Malformed JSON payload - IP: {client_ip}, "
                    f"Path: {request.path}, Error: {str(e)}"
                )
                abort(400, description="Malformed JSON payload.")
    
    def _should_skip_validation(self) -> bool:
        """Check if request should skip validation."""
        path = request.path or "/"
        
        # Skip static files
        if path.startswith("/static/"):
            return True
        
        # Skip favicon
        if path == "/favicon.ico":
            return True
        
        # Skip health check
        if path == "/healthz":
            return True
        
        # Skip documentation
        if path.startswith("/docs/"):
            return True
        
        return False
    
    def _is_authenticated_route(self) -> bool:
        """Check if the route requires authentication."""
        path = request.path or "/"
        
        # These routes don't require authentication
        public_routes = {
            "/", "/login", "/forgot-password", "/reset-password",
            "/check-email-status", "/email-sse", "/check-session",
            "/style_guide", "/healthz"
        }
        
        return path not in public_routes
    
    def _is_payload_sensitive(self) -> bool:
        """Check if the endpoint is sensitive to payload attacks."""
        path = request.path or "/"
        
        # Skip file upload routes from payload size restrictions
        upload_routes = {
            "/direct/upload", "/direct/pregraded", "/direct/pregraded/grades",
            "/remedio_zip_uploads/upload", "/direct/upload/save_image"
        }
        
        # Login and password reset endpoints are most sensitive
        sensitive_paths = {
            "/login", "/forgot-password", "/reset-password"
        }
        
        # Skip validation for upload routes
        if any(path.startswith(route) for route in upload_routes):
            return False
        
        return path in sensitive_paths
    
    def _get_max_payload_size(self) -> int:
        """Get maximum payload size based on endpoint."""
        path = request.path or "/"
        
        # Skip file upload routes - they have their own validation
        upload_routes = {
            "/direct/upload", "/direct/pregraded", "/direct/pregraded/grades",
            "/remedio_zip_uploads/upload", "/direct/upload/save_image"
        }
        
        if any(path.startswith(route) for route in upload_routes):
            # Return a large value for upload routes (they have their own validation)
            return 100 * 1024 * 1024  # 100MB
        
        # Stricter limits for authentication endpoints
        if path in ["/login", "/forgot-password", "/reset-password"]:
            # 1KB for login forms
            return 1024
        
        # 10KB for other non-authenticated endpoints
        return 10 * 1024
    
    def _get_client_ip(self) -> str:
        """Get client IP address."""
        forwarded_for = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        return forwarded_for or request.remote_addr or "-"
    
    def _handle_payload_too_large(self, e):
        """Handle payload too large errors."""
        client_ip = self._get_client_ip()
        security_logger.warning(
            f"Payload too large - IP: {client_ip}, Path: {request.path}, "
            f"Content-Length: {request.content_length}"
        )
        
        # Return JSON for API requests, HTML for others
        if request.path.startswith("/api/") or request.headers.get("Accept") == "application/json":
            return jsonify({
                "error": "Payload too large",
                "message": "Request entity too large",
                "max_size": self._get_max_payload_size()
            }), 413
        
        return jsonify({"error": "Request entity too large"}), 413
    
    def _handle_malformed_json(self, e):
        """Handle malformed JSON errors."""
        client_ip = self._get_client_ip()
        security_logger.warning(
            f"Malformed JSON - IP: {client_ip}, Path: {request.path}, "
            f"Error: {str(e)}"
        )
        
        return jsonify({"error": "Malformed JSON payload"}), 400


def validate_payload_size(max_size: Optional[int] = None) -> Callable:
    """
    Decorator to validate payload size for specific routes.
    
    Args:
        max_size: Maximum payload size in bytes. If None, uses default.
    """
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def wrapped(*args, **kwargs):
            # Get content length
            content_length = request.content_length or 0
            
            # Use provided max_size or get default
            limit = max_size or 10 * 1024  # Default 10KB
            
            if content_length > limit:
                client_ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
                client_ip = client_ip or request.remote_addr or "-"
                
                security_logger.warning(
                    f"Payload size exceeded - IP: {client_ip}, "
                    f"Path: {request.path}, Size: {content_length}, Limit: {limit}"
                )
                
                if request.path.startswith("/api/") or request.headers.get("Accept") == "application/json":
                    return jsonify({
                        "error": "Payload too large",
                        "message": f"Maximum size is {limit} bytes"
                    }), 413
                
                abort(413, description=f"Request entity too large. Maximum size is {limit} bytes.")
            
            return f(*args, **kwargs)
        
        return wrapped
    return decorator


def validate_json_structure(required_fields: Optional[list] = None) -> Callable:
    """
    Decorator to validate JSON structure for API endpoints.
    
    Args:
        required_fields: List of required fields in JSON payload
    """
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not request.is_json:
                return jsonify({"error": "Content-Type must be application/json"}), 400
            
            try:
                data = request.get_json()
                if data is None:
                    return jsonify({"error": "Invalid JSON payload"}), 400
                
                # Check required fields
                if required_fields:
                    missing_fields = [field for field in required_fields if field not in data]
                    if missing_fields:
                        return jsonify({
                            "error": "Missing required fields",
                            "missing_fields": missing_fields
                        }), 400
                
                # Store validated data for use in route
                g.validated_json = data
                
            except Exception as e:
                client_ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
                client_ip = client_ip or request.remote_addr or "-"
                
                security_logger.warning(
                    f"JSON validation failed - IP: {client_ip}, "
                    f"Path: {request.path}, Error: {str(e)}"
                )
                
                return jsonify({"error": "Malformed JSON payload"}), 400
            
            return f(*args, **kwargs)
        
        return wrapped
    return decorator


def protect_form_submission(max_fields: int = 100, max_field_length: int = 1024) -> Callable:
    """
    Decorator to protect form submissions from excessive data.
    
    Args:
        max_fields: Maximum number of form fields allowed
        max_field_length: Maximum length of each field value
    """
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def wrapped(*args, **kwargs):
            if request.method == "POST":
                # Check number of fields
                form_data = request.form.to_dict()
                if len(form_data) > max_fields:
                    client_ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
                    client_ip = client_ip or request.remote_addr or "-"
                    
                    security_logger.warning(
                        f"Too many form fields - IP: {client_ip}, "
                        f"Path: {request.path}, Fields: {len(form_data)}, Limit: {max_fields}"
                    )
                    
                    return jsonify({"error": "Too many form fields submitted"}), 400
                
                # Check field lengths
                for field_name, field_value in form_data.items():
                    if len(str(field_value)) > max_field_length:
                        client_ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
                        client_ip = client_ip or request.remote_addr or "-"
                        
                        security_logger.warning(
                            f"Form field too long - IP: {client_ip}, "
                            f"Path: {request.path}, Field: {field_name}, "
                            f"Length: {len(str(field_value))}, Limit: {max_field_length}"
                        )
                        
                        return jsonify({"error": f"Field '{field_name}' exceeds maximum length"}), 400
            
            return f(*args, **kwargs)
        
        return wrapped
    return decorator