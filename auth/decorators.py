from functools import wraps
from flask import session, request, redirect, url_for, current_app
from flask_login import current_user
import time

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
