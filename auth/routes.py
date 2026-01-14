# auth/routes.py
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import time
import logging
import base64
from flask import render_template, request, redirect, session, url_for, flash, current_app, abort, Response
from flask_login import login_user, logout_user, LoginManager, login_required, current_user
from sqlalchemy.orm import noload, selectinload
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker
from . import auth_bp
from .security import verify_password, hash_password, generate_strong_password, validate_username
from .utils import utcnow, get_client_ip
from flask import flash
from utils.rate_limiter import auth_rate_limit, rate_limit_with_feedback, rate_limit
from utils.security_middleware import protect_form_submission, validate_payload_size
from utils.log_sanitize import sanitize_log_value, mask_email
from utils.emails import generate_otp
# Note: We're using Flask-WTF's built-in CSRF protection instead of custom implementation

# Pull your shared SQLAlchemy engine & Base session factory from models
from models import engine, User, Role, LabUnit, LoginAttempt, IpLock, PasswordResetAttempt, Session  # type: ignore
from app_cache import cache
from server_side_session import mark_session_ended
from db_transaction_manager import get_db_session, transaction_scope


# Get the auth logger
auth_logger = logging.getLogger("auth")


# ----- Configurable thresholds -----
MAX_FAILS_PER_USERNAME = 5
WINDOW_USERNAME_MIN = 30

MAX_FAILS_PER_IP = 5
WINDOW_IP_MIN = 10

LOCKOUT_HOURS = 4

# ----- Flask-Login wiring -----
login_manager = LoginManager()
login_manager.login_view = "auth.login"  # where to redirect if not logged in

_USER_CACHE_TTL_SECONDS = 300

def _serialize_user_for_cache(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "full_name": user.full_name,
        "timezone": user.timezone,
        "is_active": user.is_active,
        "is_locked_until": user.is_locked_until,
        "designation": user.designation,
        "phone": user.phone,
        "hospital_id": user.hospital_id,
        "is_master_admin": getattr(user, "is_master_admin", False),
        "roles": [role.name for role in (user.roles or [])],
        "lab_units": [{"id": lu.id, "name": lu.name, "hospital_id": lu.hospital_id} for lu in (user.lab_units or [])],
    }


def _build_user_from_cache(payload: dict) -> User:
    user = User()
    user.id = payload.get("id")
    user.username = payload.get("username")
    user.email = payload.get("email")
    user.full_name = payload.get("full_name")
    user.timezone = payload.get("timezone")
    user.is_active = payload.get("is_active", True)
    user.is_locked_until = payload.get("is_locked_until")
    user.designation = payload.get("designation")
    user.phone = payload.get("phone")
    user.hospital_id = payload.get("hospital_id")
    user.is_master_admin = payload.get("is_master_admin", False)
    roles = [Role(name=name) for name in payload.get("roles", [])]
    user.roles = roles
    
    # Reconstruct lab units
    lab_units = []
    for lu_data in payload.get("lab_units", []):
        lu = LabUnit(id=lu_data["id"], name=lu_data["name"], hospital_id=lu_data["hospital_id"])
        lab_units.append(lu)
    user.lab_units = lab_units
    
    return user


@login_manager.user_loader
def load_user(user_id: str):
    cache_key = f"auth:user:{user_id}"
    try:
        cached = cache.get(cache_key)
    except Exception as e:
        auth_logger.warning("Cache get failed: %s", sanitize_log_value(e))
        cached = None
    if cached:
        return _build_user_from_cache(cached)

    # Use shared session from the transaction manager
    from db_transaction_manager import get_db_session
    with get_db_session() as db:
        from sqlalchemy.orm import joinedload
        user = db.execute(
            select(User)
            .options(
                joinedload(User.roles),
                joinedload(User.lab_units),
                joinedload(User.hospital),
            )
            .where(User.id == int(user_id))
        ).unique().scalar_one_or_none()
        
        if user:
            try:
                cache.set(cache_key, _serialize_user_for_cache(user), timeout=_USER_CACHE_TTL_SECONDS)
            except Exception as e:
                auth_logger.warning("Cache set failed: %s", sanitize_log_value(e))
        return user

# ----- Helpers -----
def _is_ip_locked(db, ip: str):
    rec = db.execute(select(IpLock).where(IpLock.ip_address == ip)).scalar_one_or_none()
    if rec:
        # Ensure both datetimes are timezone-aware for comparison
        rec_locked_until = rec.locked_until
        if rec_locked_until.tzinfo is None:
            from datetime import timezone
            rec_locked_until = rec_locked_until.replace(tzinfo=timezone.utc)
        
        current_time = utcnow()
        if current_time.tzinfo is None:
            from datetime import timezone
            current_time = current_time.replace(tzinfo=timezone.utc)
            
        if rec_locked_until > current_time:
            return True, rec.locked_until
    return False, None

def _lock_ip(db, ip: str):
    until = utcnow() + timedelta(hours=LOCKOUT_HOURS)
    rec = db.execute(select(IpLock).where(IpLock.ip_address == ip)).scalar_one_or_none()
    if rec:
        rec.locked_until = until
    else:
        db.add(IpLock(ip_address=ip, locked_until=until))
    return until

def _lock_user(db, user: User):
    user.is_locked_until = utcnow() + timedelta(hours=LOCKOUT_HOURS)
    db.add(user)
    return user.is_locked_until

def _recent_failed_by_username(db, username_input: str):
    since = utcnow() - timedelta(minutes=WINDOW_USERNAME_MIN)
    q = select(func.count()).select_from(LoginAttempt).where(
        func.lower(LoginAttempt.username_input) == func.lower(username_input),
        LoginAttempt.success == False,  # noqa: E712
        LoginAttempt.created_at >= since
    )
    return db.execute(q).scalar() or 0

def _recent_failed_by_ip(db, ip: str):
    since = utcnow() - timedelta(minutes=WINDOW_IP_MIN)
    q = select(func.count()).select_from(LoginAttempt).where(
        LoginAttempt.ip_address == ip,
        LoginAttempt.success == False,  # noqa: E712
        LoginAttempt.created_at >= since
    )
    return db.execute(q).scalar() or 0

def _record_attempt(db, username_input: str, ip: str, success: bool):
    db.add(LoginAttempt(username_input=username_input, ip_address=ip, success=success))

def _recent_password_reset_attempts_by_email(db, email: str):
    """Check how many password reset attempts were made for the email today."""
    today_start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    q = select(func.count()).select_from(PasswordResetAttempt).where(
        func.lower(PasswordResetAttempt.email) == func.lower(email),
        PasswordResetAttempt.attempted_at >= today_start
    )
    return db.execute(q).scalar() or 0

def _record_password_reset_attempt(db, email: str, ip: str):
    """Record a password reset attempt."""
    db.add(PasswordResetAttempt(email=email, ip_address=ip))

def _clear_password_reset_session(session):
    """
    Clear all password reset session data.

    Helper function to securely clean up session data after
    password reset completion or failure.

    Args:
        session: Flask session object
    """
    session.pop('password_reset_otp_hashed', None)
    session.pop('password_reset_email', None)
    session.pop('password_reset_expiry', None)
    session.pop('password_reset_user_id', None)
    session.pop('password_reset_otp_used', None)

# Global storage for user-specific events (in production, use Redis or similar)
# This is a simple in-memory storage for demo purposes
from collections import defaultdict
email_sending_results = defaultdict(list)


def _push_email_result(user_id: str, result: dict):
    """Push an email sending result to the user's queue."""
    email_sending_results[user_id].append(result)


def _get_email_results(user_id: str):
    """Get and clear email results for a user."""
    results = email_sending_results[user_id]
    email_sending_results[user_id] = []  # Clear the queue
    return results

# ----- Routes -----
@auth_bp.route("/login", methods=["GET", "POST"])
@rate_limit_with_feedback("20 per minute", show_warning=True)
@protect_form_submission(max_fields=6, max_field_length=255)  # 6 fields, 255 for password, reasonable limits for others
@validate_payload_size(max_size=768)  # 768 bytes - more restrictive than 1KB
def login():
    from flask_login import current_user
    from utils.captcha import captcha_manager
    
    # Log at the very beginning to catch all requests
    ip = get_client_ip()
    auth_logger.info(
        "Login route accessed - Method: %s, IP: %s, User-Agent: %s",
        sanitize_log_value(request.method),
        sanitize_log_value(ip),
        sanitize_log_value(request.headers.get("User-Agent", "Unknown")),
    )
    
    # If user is already logged in, redirect to homepage
    if current_user.is_authenticated:
        flash("You are already Logged In.", "info")
        # Role-based landing pages for already logged in users
        if current_user.has_role('ophthalmologist'):
            return redirect(url_for("grading.index"))
        if current_user.has_role('fileUploader') or current_user.has_role('optometrist'):
            return redirect(url_for("direct_uploads.upload_index"))
        return redirect(url_for("homepage"))
    
    ip = get_client_ip()
    with transaction_scope() as db:
        # Block if IP locked
        ip_locked, ip_until = _is_ip_locked(db, ip)
        if ip_locked:
            # Convert to user's timezone for display
            from utils.datetime_filters import format_user_datetime
            formatted_time = format_user_datetime(ip_until)
            return render_template("auth/login.html",
                                   error=f"This IP is temporarily locked until {formatted_time}.")
        
        if request.method == "POST":
            # Flask-WTF CSRF protection is automatically applied
            # No need for manual validation here
            
            # Log POST request details for debugging (excluding sensitive data)
            form_data = dict(request.form)
            # Remove sensitive fields before logging
            sensitive_fields = ['password', 'csrf_token', 'new_password', 'confirm_password']
            safe_form_data = {k: v for k, v in form_data.items() if k not in sensitive_fields}
            auth_logger.info(
                "POST request received - Form data (sanitized): %s",
                sanitize_log_value(safe_form_data),
            )
            auth_logger.info(
                "POST request headers - Content-Type: %s, Content-Length: %s",
                sanitize_log_value(request.content_type),
                sanitize_log_value(request.content_length),
            )
            
            username = (request.form.get("username") or "").strip()
            password = request.form.get("password") or ""
            captcha_input = (request.form.get("captcha") or "").strip()
            
            # Log login attempt
            auth_logger.info(
                "Login attempt - User: %s, IP: %s",
                sanitize_log_value(username),
                sanitize_log_value(ip),
            )
            
            # Validate CAPTCHA first
            auth_logger.info(
                "CAPTCHA validation attempt - Input: '%s'",
                sanitize_log_value(captcha_input),
            )
            captcha_valid, captcha_message = captcha_manager.validate_captcha(captcha_input)
            auth_logger.info(
                "CAPTCHA validation result - Valid: %s, Message: %s",
                sanitize_log_value(captcha_valid),
                sanitize_log_value(captcha_message),
            )
            
            if not captcha_valid:
                # Generate new CAPTCHA only when validation fails
                captcha_data = captcha_manager.generate_captcha()
                auth_logger.info(
                    "CAPTCHA validation failed - New CAPTCHA generated: %s",
                    sanitize_log_value(captcha_data.get("captcha_id")),
                )
                return render_template("auth/login.html",
                                       error=captcha_message,
                                       captcha_image=captcha_data['image'],
                                       captcha_data=captcha_data)

            # Per-username failed window check (before verifying to avoid enumeration timing side-channel)
            recent_user_fails = _recent_failed_by_username(db, username)
            if recent_user_fails >= MAX_FAILS_PER_USERNAME:
                # If user exists, lock them now
                user = db.execute(select(User).where(func.lower(User.username) == func.lower(username))).scalar_one_or_none()
                if user:
                    until = _lock_user(db, user)
                    _record_attempt(db, username, ip, success=False)
                    # Convert to user's timezone for display
                    from utils.datetime_filters import format_user_datetime
                    formatted_time = format_user_datetime(until)
                    # Generate new CAPTCHA for error response
                    captcha_data = captcha_manager.generate_captcha()
                    return render_template("auth/login.html",
                                           error=f"User locked due to repeated failures until {formatted_time}.",
                                           captcha_image=captcha_data['image'],
                                           captcha_data=captcha_data)
                # If user doesn't exist, still fall through and verify → will fail & increase counters,
                # but we won't create a fake user. The IP rule will still protect.

            # Per-IP failed window check
            recent_ip_fails = _recent_failed_by_ip(db, ip)
            if recent_ip_fails >= MAX_FAILS_PER_IP:
                until = _lock_ip(db, ip)
                _record_attempt(db, username, ip, success=False)
                # Convert to user's timezone for display
                from utils.datetime_filters import format_user_datetime
                formatted_time = format_user_datetime(until)
                # Generate new CAPTCHA for error response
                captcha_data = captcha_manager.generate_captcha()
                return render_template("auth/login.html",
                                       error=f"This IP is locked due to repeated failures until {formatted_time}.",
                                       captcha_image=captcha_data['image'],
                                       captcha_data=captcha_data)

            # Fetch user & enforce user lock
            user = db.execute(select(User).where(func.lower(User.username) == func.lower(username))).scalar_one_or_none()
            if user and user.is_locked_until:
                # Ensure both datetimes are timezone-aware for comparison
                user_locked_until = user.is_locked_until
                if user_locked_until.tzinfo is None:
                    from datetime import timezone
                    user_locked_until = user_locked_until.replace(tzinfo=timezone.utc)
                
                current_time = utcnow()
                if current_time.tzinfo is None:
                    from datetime import timezone
                    current_time = current_time.replace(tzinfo=timezone.utc)
                
                if user_locked_until > current_time:
                    _record_attempt(db, username, ip, success=False)
                    # Convert to user's timezone for display
                    from utils.datetime_filters import format_user_datetime
                    formatted_time = format_user_datetime(user.is_locked_until)
                    # Generate new CAPTCHA for error response
                    captcha_data = captcha_manager.generate_captcha()
                    return render_template("auth/login.html",
                                           error=f"User is locked until {formatted_time}.",
                                           captcha_image=captcha_data['image'],
                                           captcha_data=captcha_data)

            # Verify password
            if user and user.is_active and verify_password(user.password_hash, password):
                _record_attempt(db, username, ip, success=True)
                login_user(user)

                # Start sliding inactivity window
                session.permanent = True  # enable cookie expiration control
                session["last_active"] = int(time.time())

                # SECURITY: Flag this as a new login for session rotation
                # This will trigger invalidation of other sessions in save_session()
                session["_fresh_login"] = True
                session.modified = True

                # Log successful login with session ID
                session_id = session.get('_id', 'unknown')
                auth_logger.info(
                    "User login successful - User: %s, IP: %s, SessionID: %s, UserID: %s",
                    sanitize_log_value(username),
                    sanitize_log_value(ip),
                    sanitize_log_value(session_id),
                    sanitize_log_value(user.id),
                )

                # Role-based landing pages
                if user.has_role('ophthalmologist'):
                    return redirect(url_for("grading.index"))
                if user.has_role('fileUploader') or user.has_role('optometrist'):
                    return redirect(url_for("direct_uploads.upload_index"))

                # Optional: rotate session / set remember as needed
                return redirect(url_for("homepage"))

            # Failure path
            _record_attempt(db, username, ip, success=False)

            # Re-check windows after this failure to possibly trigger locks
            if _recent_failed_by_username(db, username) >= MAX_FAILS_PER_USERNAME and user:
                until = _lock_user(db, user)
                # Convert to user's timezone for display
                from utils.datetime_filters import format_user_datetime
                formatted_time = format_user_datetime(until)
                # Generate new CAPTCHA for error response
                captcha_data = captcha_manager.generate_captcha()
                return render_template("auth/login.html",
                                       error=f"User locked due to repeated failures until {formatted_time}.",
                                       captcha_image=captcha_data['image'],
                                       captcha_data=captcha_data)
            if _recent_failed_by_ip(db, ip) >= MAX_FAILS_PER_IP:
                until = _lock_ip(db, ip)
                # Convert to user's timezone for display
                from utils.datetime_filters import format_user_datetime
                formatted_time = format_user_datetime(until)
                # Generate new CAPTCHA for error response
                captcha_data = captcha_manager.generate_captcha()
                return render_template("auth/login.html",
                                       error=f"This IP is locked due to repeated failures until {formatted_time}.",
                                       captcha_image=captcha_data['image'],
                                       captcha_data=captcha_data)

            # Generic error (avoid username enumeration)
            # Generate new CAPTCHA for error response
            captcha_data = captcha_manager.generate_captcha()
            return render_template("auth/login.html",
                                   error="Invalid username or password.",
                                   captcha_image=captcha_data['image'],
                                   captcha_data=captcha_data)

        # GET - Initialize session and render login page
        # Force session modification to ensure cookie is set
        session["_session_initialized"] = True
        session.modified = True

        auth_logger.info(
            "GET request - Session initialized, keys: %s",
            sanitize_log_value(list(session.keys())),
        )
        auth_logger.info(f"GET request - Session cookie will be set")

        return render_template("auth/login.html")

@auth_bp.route("/refresh-captcha")
@rate_limit("10 per minute")
def refresh_captcha():
    """Return a new CAPTCHA image as JSON."""
    from utils.captcha import captcha_manager
    from flask import jsonify
    
    # Log refresh request for debugging
    ip = get_client_ip()
    auth_logger.info(
        "CAPTCHA refresh request - IP: %s",
        sanitize_log_value(ip),
    )
    
    captcha_data = captcha_manager.generate_captcha()
    auth_logger.info(
        "CAPTCHA refresh generated - ID: %s",
        sanitize_log_value(captcha_data.get("captcha_id")),
    )
    
    # Create JSON response
    response = jsonify(captcha_data)
    
    # Add headers to prevent caching
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    
    return response

@auth_bp.route("/captcha-audio")
@rate_limit("10 per minute")
def captcha_audio():
    """Return CAPTCHA audio as WAV file."""
    from utils.captcha import captcha_manager
    from flask import session, Response
    
    # Check if CAPTCHA exists in session
    if 'captcha_text' not in session:
        return Response("No CAPTCHA found", status=404)
    
    # Check if CAPTCHA has expired
    captcha_expiry = session.get('captcha_expiry', 0)
    # Handle both ISO string and float timestamp formats
    try:
        if isinstance(captcha_expiry, str):
            # Parse ISO format datetime string
            from datetime import datetime, timezone
            expiry_time = datetime.fromisoformat(captcha_expiry)
            # Ensure timezone-aware comparison
            if expiry_time.tzinfo is None:
                expiry_time = expiry_time.replace(tzinfo=timezone.utc)
            current_time = datetime.now(timezone.utc)
            is_expired = current_time > expiry_time
        else:
            # Handle as timestamp (legacy format)
            expiry_time = float(captcha_expiry)
            is_expired = expiry_time < time.time()
    except (ValueError, TypeError):
        return Response("Invalid CAPTCHA expiry format", status=400)
    
    if is_expired:
        return Response("CAPTCHA expired", status=410)
    
    # Generate audio for current CAPTCHA
    captcha_text = session.get('captcha_text', '')
    audio_data = captcha_manager.generate_captcha_audio(captcha_text)
    
    if not audio_data:
        return Response("Audio generation failed", status=500)
    
    # Extract base64 data from data URL
    if audio_data.startswith('data:audio/wav;base64,'):
        audio_bytes = base64.b64decode(audio_data.split(',')[1])
        
        # Return as WAV file
        return Response(
            audio_bytes,
            mimetype='audio/wav',
            headers={
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0'
            }
        )
    
    return Response("Audio format error", status=500)

@auth_bp.route("/logout", methods=["POST", "GET"])
@login_required
@rate_limit("30 per minute")
def logout():
    # Log logout event
    username = getattr(current_user, 'username', 'Unknown')
    user_id = getattr(current_user, 'id', 'Unknown')
    ip = get_client_ip()
    cookie_name = current_app.config.get("SESSION_COOKIE_NAME", "session")
    prior_session_id = getattr(session, "session_id", None) or request.cookies.get(cookie_name)
    auth_logger.info(
        "User logout - User: %s, UserID: %s, IP: %s, SessionID: %s",
        sanitize_log_value(username),
        sanitize_log_value(user_id),
        sanitize_log_value(ip),
        sanitize_log_value(prior_session_id),
    )
    try:
        session_user_id = int(current_user.get_id())  # type: ignore[arg-type]
    except (TypeError, ValueError):
        session_user_id = None
    logout_user()
    session.clear()
    session.modified = True
    mark_session_ended(prior_session_id, session_user_id)
    flash("You have been signed out.", "info")
    return redirect(url_for("homepage"))



@auth_bp.get("/ping")
@login_required
def ping():
    # Not strictly necessary (your before_request already updates),
    # but we also update here so the button works even on pages with no other requests.
    session.permanent = True
    session["last_active"] = int(time.time())
    session.modified = True
    return {"ok": True, "ts": int(time.time())}


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
@auth_rate_limit("10 per 5 minutes")  # Slightly less restrictive for user convenience
@protect_form_submission(max_fields=3, max_field_length=254)  # Email max length is 254 chars per RFC
@validate_payload_size(max_size=512)  # 512B limit - more restrictive for single email field
def forgot_password():
    """
    Route to handle forgot password functionality.
    Generates an 8-character alphanumeric OTP and emails it to the user's email address.
    """
    from datetime import datetime, timedelta, timezone
    import secrets
    from utils.emails import send_otp_email
    from sqlalchemy import and_
    
    def email_callback(success, session_id):
        result = {
            'success': success,
            'timestamp': datetime.now(timezone.utc),
            'type': 'email_result'
        }
        if success:
            result['message'] = "OTP sent successfully"
        else:
            result['message'] = "Email sending failed due to server error. Please contact support."
        
        # Push to user-specific queue using session ID as user identifier
        _push_email_result(session_id, result)
    
    if request.method == "POST":
        # Flask-WTF CSRF protection is automatically applied
        # No need for manual validation here
        email = request.form.get("email", "").strip()
        username = request.form.get("username", "").strip()
        ip = get_client_ip()
        
        # Validate email format
        if not email or "@" not in email:
            flash("Please enter a valid email address.", "error")
            return render_template("auth/forgot_password.html")

        is_valid_username, username_error = validate_username(username)
        if not is_valid_username:
            flash(username_error, "error")
            return render_template("auth/forgot_password.html")
        
        with transaction_scope() as db:
            # Find user by email
            user = db.query(User).filter(
                func.lower(User.email) == func.lower(email),
                func.lower(User.username) == func.lower(username),
            ).first()
            
            # Check if there have been too many reset attempts today
            reset_attempts_today = _recent_password_reset_attempts_by_email(db, email)
            if reset_attempts_today >= 5:
                flash("Too many password reset attempts. Please try again tomorrow.", "error")
                return render_template("auth/forgot_password.html")
            
            # Record password reset attempt
            _record_password_reset_attempt(db, email, ip)

            # If user exists, proceed with OTP generation and sending
            if user:
                # Generate a secure 16-character OTP using centralized utility
                otp = generate_otp(length=16)

                # SECURITY: Store hashed OTP in session, not plaintext
                # This prevents OTP extraction if session database is compromised
                session['password_reset_otp_hashed'] = hash_password(otp)
                session['password_reset_email'] = email
                session['password_reset_expiry'] = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
                session['password_reset_user_id'] = user.id
                session['password_reset_otp_used'] = False  # One-time use flag

                # Send email with OTP asynchronously
                session_id = session.get('_id', 'unknown')
                send_otp_email(
                    email,
                    user.username,
                    otp,
                    callback=lambda success: email_callback(success, session_id),
                )

                # To prevent user enumeration, always show the same initial message regardless of email sending result
                flash("If an account exists with that email address, an OTP has been sent to it. Please check your inbox.", "success")

                return redirect(url_for("auth.reset_password"))
            else:
                # To prevent user enumeration, we still show the same message
                flash("If an account exists with that email address, an OTP has been sent to it. Please check your inbox.", "success")
                return redirect(url_for("auth.reset_password"))
    
    # GET request
    return render_template("auth/forgot_password.html")


@auth_bp.route("/reset-password", methods=["GET", "POST"])
@auth_rate_limit("10 per 5 minutes")  # Slightly less restrictive for user convenience
@protect_form_submission(max_fields=5, max_field_length=200)
@validate_payload_size(max_size=2048)  # 2KB limit for reset password form
def reset_password():
    """
    Route to handle password reset with OTP verification.
    """
    from datetime import datetime, timezone
    from utils.emails import send_password_reset_email
    
    if request.method == "POST":
        # Flask-WTF CSRF protection is automatically applied
        # No need for manual validation here
        ip = get_client_ip()
        otp = request.form.get("otp", "").strip()

        # Validate inputs
        if not otp:
            flash("Please enter the OTP.", "error")
            return render_template("auth/reset_password.html")

        # Verify OTP from session (now using hashed OTP)
        session_otp_hashed = session.get('password_reset_otp_hashed')
        session_email = session.get('password_reset_email')
        session_expiry = session.get('password_reset_expiry')
        session_user_id = session.get('password_reset_user_id')
        session_otp_used = session.get('password_reset_otp_used', False)

        if not all([session_otp_hashed, session_email, session_expiry, session_user_id]):
            flash("Invalid or expired OTP. Please request a new one.", "error")
            return redirect(url_for("auth.forgot_password"))

        # Check if OTP has already been used (one-time use protection)
        if session_otp_used:
            flash("This OTP has already been used. Please request a new one.", "error")
            _clear_password_reset_session(session)
            return redirect(url_for("auth.forgot_password"))

        # Check if OTP has expired
        expiry_time = datetime.fromisoformat(session_expiry)
        current_time = datetime.now(timezone.utc)

        # Ensure both datetimes are timezone-aware for comparison
        if expiry_time.tzinfo is None:
            expiry_time = expiry_time.replace(tzinfo=timezone.utc)
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=timezone.utc)

        if current_time > expiry_time:
            flash("OTP has expired. Please request a new one.", "error")
            _clear_password_reset_session(session)
            return redirect(url_for("auth.forgot_password"))

        # SECURITY: Use constant-time comparison for OTP verification
        # This prevents timing attacks that could reveal valid OTPs
        if not verify_password(session_otp_hashed, otp):
            flash("Invalid OTP. Please try again.", "error")
            return render_template("auth/reset_password.html")

        # Mark OTP as used (one-time use protection)
        session['password_reset_otp_used'] = True

        with transaction_scope() as db:
            user = db.get(User, session_user_id)
            if user is None or (user.email or "").lower() != session_email.lower():
                flash("Unable to reset password for this account. Please request a new OTP.", "error")
                _clear_password_reset_session(session)
                return redirect(url_for("auth.forgot_password"))

            generated_password = generate_strong_password()
            user.password_hash = hash_password(generated_password)
            user.updated_at = datetime.now(timezone.utc)
            db.add(user)

            # Capture user information before session ends
            username = user.username
            email = user.email
            user_id = user.id

        _clear_password_reset_session(session)

        # Log successful password reset
        session_id = session.get('_id', 'unknown')
        auth_logger.info(
            "Password reset successful - User: %s, Email: %s, IP: %s, SessionID: %s, UserID: %s",
            sanitize_log_value(username),
            mask_email(email),
            sanitize_log_value(ip),
            sanitize_log_value(session_id),
            sanitize_log_value(user_id),
        )

        send_password_reset_email(email, username, generated_password)

        return render_template(
            "auth/reset_password_success.html",
            username=username,
            generated_password=generated_password,
        )

    return render_template("auth/reset_password.html")


@auth_bp.route("/email-sse")
@rate_limit("30 per minute")  # SSE endpoint for real-time updates
def email_sse():
    """Server-sent events endpoint for email sending results."""
    def event_stream():
        while True:
            # Get user-specific results
            session_id = session.get('_id', 'unknown')
            results = _get_email_results(session_id)
            
            for result in results:
                yield f"data: {result}\n\n"
            
            time.sleep(1)  # Poll every second
    
    return Response(event_stream(), mimetype="text/plain")


@auth_bp.route("/check-email-status")
@rate_limit("60 per minute")  # Status check endpoint
def check_email_status():
    """Check for any email sending status updates."""
    session_id = session.get('_id', 'unknown')
    results = _get_email_results(session_id)
    # Convert datetime objects to strings for JSON serialization
    serializable_results = []
    for result in results:
        serializable_result = result.copy()
        if isinstance(result.get('timestamp'), datetime):
            serializable_result['timestamp'] = result['timestamp'].isoformat()
        serializable_results.append(serializable_result)
    return {"results": serializable_results}


@auth_bp.route("/check-session")
@rate_limit("30 per minute")  # Session check endpoint
def check_session():
    """Check if session cookie is valid and redirect to homepage if it is."""
    from flask_login import current_user
    if current_user.is_authenticated:
        return redirect(url_for("homepage"))
    else:
        # If not authenticated, redirect to login
        return redirect(url_for("auth.login"))

@auth_bp.route("/confirm-password", methods=["GET", "POST"])
@login_required
@rate_limit("10 per minute")
def confirm_password():
    """
    Route for re-authentication confirmation.
    Used by @reauth_required decorator.
    """
    next_url = request.args.get('next') or request.form.get('next') or url_for('homepage')
    
    # Get user safely to avoid DetachedInstanceError
    from db_transaction_manager import get_db_session
    user_to_verify = current_user
    
    # In some contexts (like tests), current_user might be a detached proxy.
    # We'll use the session ID to re-fetch if needed for password verification
    user_id = session.get('_user_id')
    
    if request.method == "POST":
        password = request.form.get('confirm_password')
        
        verified = False
        if user_id:
             with get_db_session() as db:
                user = db.query(User).filter(User.id == int(user_id)).first()
                if user and verify_password(user.password_hash, password):
                    verified = True
        elif verify_password(current_user.password_hash, password):
             verified = True

        if verified:
            # Update last_sudo_time
            session['last_sudo_time'] = int(time.time())
            session.modified = True
            
            # Log success
            ip = get_client_ip()
            auth_logger.info(
                "Re-authentication successful - UserID: %s, IP: %s",
                sanitize_log_value(user_id),
                sanitize_log_value(ip)
            )
            
            flash("Identity confirmed.", "success")
            return redirect(next_url)
        else:
            # Low-level failure logging
            ip = get_client_ip()
            auth_logger.warning(
                "Re-authentication failed (invalid password) - UserID: %s, IP: %s",
                sanitize_log_value(user_id),
                sanitize_log_value(ip)
            )
            flash("Invalid password. Please try again.", "danger")
    
    # Extract operation name from next URL for display context
    operation_name = "Sensitive Operation"
    if 'admin' in next_url:
        parts = next_url.strip('/').split('/')
        if len(parts) > 1:
            operation_name = parts[-1].replace('-', ' ').title()

    return render_template(
        "admin/reauth_confirm.html",
        operation_name=operation_name,
        return_url=url_for('auth.confirm_password', next=next_url),
        current_user=current_user
    )
