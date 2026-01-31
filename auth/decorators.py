import os
import jwt
import logging
from functools import wraps
from flask import session, request, redirect, url_for, current_app, jsonify
from flask_login import current_user
import time
from utils.log_sanitize import sanitize_log_value

logger = logging.getLogger("auth.decorators")

def token_auth_required(f):
    """
    Decorator to require a valid JWT token in the Authorization header.
    Also signals to the global session-based login guard that this route 
    handles its own authentication.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        jwt_secret = os.environ.get("JWT_SECRET")
        if not jwt_secret:
            logger.error("JWT_SECRET not configured")
            return jsonify({"message": "Server configuration error"}), 500

        token = None
        if "Authorization" in request.headers:
            auth_header = request.headers["Authorization"]
            if auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]
        
        if not token:
            return jsonify({"message": "Token is missing"}), 401
        
        try:
            # We use HS256 by default for mobile device tokens
            data = jwt.decode(token, jwt_secret, algorithms=["HS256"])
            request.mobile_claims = data
        except jwt.ExpiredSignatureError:
            return jsonify({"message": "Token has expired"}), 401
        except jwt.InvalidTokenError as e:
            logger.warning("Invalid token attempt: %s", sanitize_log_value(str(e)))
            return jsonify({"message": "Invalid token"}), 401
            
        return f(*args, **kwargs)
    
    # Set signal attribute for app.py guards
    decorated._token_auth_applied = True
    return decorated

def reauth_required(timeout=600):
    """
    Decorator to force re-authentication if the session's sensitive operation
    token (last_sudo_time) is older than `timeout` seconds.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return current_app.login_manager.unauthorized()

            last_sudo = session.get('last_sudo_time')
            now = int(time.time())
            
            if not last_sudo or (now - last_sudo) > timeout:
                return redirect(url_for('auth.confirm_password', next=request.url))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator
