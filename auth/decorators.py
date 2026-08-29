import logging
import os
import time
from functools import wraps

import jwt
from flask import current_app, jsonify, redirect, request, session, url_for
from flask_login import current_user

from db_transaction_manager import get_db_session
from services.mobile.auth_sessions import MobileAuthError, validate_access_session
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
            if data.get("typ") and data.get("typ") != "access":
                return jsonify({"message": "Invalid token type"}), 401

            user_id = data.get("sub")
            mobile_auth = {
                "claims": data,
                "user_id": int(user_id) if user_id is not None else None,
            }

            with get_db_session() as db:
                access_context = validate_access_session(db, data)
                mobile_auth["mobile_session_id"] = access_context.session.id
                mobile_auth["session_id"] = access_context.session.id
                mobile_auth["device_id"] = access_context.session.device_id
                mobile_auth["user_id"] = access_context.user.id
                mobile_auth["user"] = {
                    "id": access_context.user.id,
                    "username": access_context.user.username,
                    "hospital_id": access_context.user.hospital_id,
                }

            request.mobile_auth = mobile_auth
            request.mobile_claims = data
        except jwt.ExpiredSignatureError:
            return jsonify({"message": "Token has expired"}), 401
        except MobileAuthError as e:
            return jsonify({"message": e.message}), e.status_code
        except jwt.InvalidTokenError as e:
            logger.warning("Invalid token attempt: %s", sanitize_log_value(str(e)))
            return jsonify({"message": "Invalid token"}), 401
            
        return f(*args, **kwargs)
    
    # Set signal attribute for app.py guards
    decorated._token_auth_applied = True
    return decorated


def session_or_token_auth_required(f):
    """Accept an authenticated web session or a validated mobile bearer session."""
    token_wrapped = token_auth_required(f)

    @wraps(f)
    def decorated(*args, **kwargs):
        if current_user.is_authenticated:
            return f(*args, **kwargs)
        return token_wrapped(*args, **kwargs)

    # Hybrid routes retain CSRF/session checks for web requests while the app
    # guard permits requests carrying a bearer token to reach this decorator.
    decorated._session_or_token_auth_applied = True
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


def require_recent_reauthentication(timeout=600):
    """Return a reauthentication response, or ``None`` when step-up is fresh."""
    if not current_user.is_authenticated:
        return current_app.login_manager.unauthorized()
    last_sudo = session.get("last_sudo_time")
    now = int(time.time())
    if not last_sudo or (now - last_sudo) > timeout:
        return redirect(url_for("auth.confirm_password", next=request.url))
    return None
