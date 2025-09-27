# auth/routes.py
from __future__ import annotations
from datetime import timedelta
import time
import logging
from flask import render_template, request, redirect, session, url_for, flash, current_app, abort
from flask_login import login_user, logout_user, LoginManager, login_required, current_user
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker
from . import auth_bp
from .security import verify_password, hash_password
from .utils import utcnow, get_client_ip
from flask import flash

# Pull your shared SQLAlchemy engine & Base session factory from models
from models import engine, User, LoginAttempt, IpLock  # type: ignore

# Get the auth logger
auth_logger = logging.getLogger("auth")

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

# ----- Configurable thresholds -----
MAX_FAILS_PER_USERNAME = 5
WINDOW_USERNAME_MIN = 30

MAX_FAILS_PER_IP = 5
WINDOW_IP_MIN = 10

LOCKOUT_HOURS = 4

# ----- Flask-Login wiring -----
login_manager = LoginManager()
login_manager.login_view = "auth.login"  # where to redirect if not logged in

@login_manager.user_loader
def load_user(user_id: str):
    with SessionLocal() as db:
        return db.get(User, int(user_id))

# ----- Helpers -----
def _is_ip_locked(db, ip: str):
    rec = db.execute(select(IpLock).where(IpLock.ip_address == ip)).scalar_one_or_none()
    if rec and rec.locked_until > utcnow():
        return True, rec.locked_until
    return False, None

def _lock_ip(db, ip: str):
    until = utcnow() + timedelta(hours=LOCKOUT_HOURS)
    rec = db.execute(select(IpLock).where(IpLock.ip_address == ip)).scalar_one_or_none()
    if rec:
        rec.locked_until = until
    else:
        db.add(IpLock(ip_address=ip, locked_until=until))
    db.commit()
    return until

def _lock_user(db, user: User):
    user.is_locked_until = utcnow() + timedelta(hours=LOCKOUT_HOURS)
    db.add(user); db.commit()
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
    db.commit()

# ----- Routes -----
@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    ip = get_client_ip()
    with SessionLocal() as db:
        # Block if IP locked
        ip_locked, ip_until = _is_ip_locked(db, ip)
        if ip_locked:
            return render_template("auth/login.html",
                                   error=f"This IP is temporarily locked until {ip_until.isoformat()}."),
        if request.method == "POST":
            username = (request.form.get("username") or "").strip()
            password = request.form.get("password") or ""

            # Per-username failed window check (before verifying to avoid enumeration timing side-channel)
            recent_user_fails = _recent_failed_by_username(db, username)
            if recent_user_fails >= MAX_FAILS_PER_USERNAME:
                # If user exists, lock them now
                user = db.execute(select(User).where(func.lower(User.username) == func.lower(username))).scalar_one_or_none()
                if user:
                    until = _lock_user(db, user)
                    _record_attempt(db, username, ip, success=False)
                    return render_template("auth/login.html",
                                           error=f"User locked due to repeated failures until {until.isoformat()}.")
                # If user doesn't exist, still fall through and verify → will fail & increase counters,
                # but we won't create a fake user. The IP rule will still protect.

            # Per-IP failed window check
            recent_ip_fails = _recent_failed_by_ip(db, ip)
            if recent_ip_fails >= MAX_FAILS_PER_IP:
                until = _lock_ip(db, ip)
                _record_attempt(db, username, ip, success=False)
                return render_template("auth/login.html",
                                       error=f"This IP is locked due to repeated failures until {until.isoformat()}.")

            # Fetch user & enforce user lock
            user = db.execute(select(User).where(func.lower(User.username) == func.lower(username))).scalar_one_or_none()
            if user and user.is_locked_until and user.is_locked_until > utcnow():
                _record_attempt(db, username, ip, success=False)
                return render_template("auth/login.html",
                                       error=f"User is locked until {user.is_locked_until.isoformat()}.")

            # Verify password
            if user and user.is_active and verify_password(user.password_hash, password):
                _record_attempt(db, username, ip, success=True)
                login_user(user)
                # Log successful login
                auth_logger.info(f"Successful login - User: {username}, IP: {ip}")
                # Start sliding inactivity window
                session.permanent = True  # enable cookie expiration control
                session["last_active"] = int(time.time())
                session.modified = True

                # Optional: rotate session / set remember as needed
                return redirect(url_for("homepage"))

            # Failure path
            _record_attempt(db, username, ip, success=False)
            # Log failed login attempt
            auth_logger.warning(f"Failed login attempt - User: {username}, IP: {ip}")

            # Re-check windows after this failure to possibly trigger locks
            if _recent_failed_by_username(db, username) >= MAX_FAILS_PER_USERNAME and user:
                until = _lock_user(db, user)
                auth_logger.warning(f"User locked due to repeated failures - User: {username}, IP: {ip}, Until: {until.isoformat()}")
                return render_template("auth/login.html",
                                       error=f"User locked due to repeated failures until {until.isoformat()}.")
            if _recent_failed_by_ip(db, ip) >= MAX_FAILS_PER_IP:
                until = _lock_ip(db, ip)
                auth_logger.warning(f"IP locked due to repeated failures - IP: {ip}, Until: {until.isoformat()}")
                return render_template("auth/login.html",
                                       error=f"This IP is locked due to repeated failures until {until.isoformat()}.")

            # Generic error (avoid username enumeration)
            return render_template("auth/login.html", error="Invalid username or password.")

        # GET
        return render_template("auth/login.html")

@auth_bp.route("/logout", methods=["POST", "GET"])
@login_required
def logout():
    # Log logout event
    username = getattr(current_user, 'username', 'Unknown')
    ip = get_client_ip()
    auth_logger.info(f"User logout - User: {username}, IP: {ip}")
    logout_user()
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
def forgot_password():
    """
    Route to handle forgot password functionality.
    Generates an 8-character alphanumeric OTP and emails it to the user's email address.
    """
    from datetime import datetime, timedelta
    import secrets
    from models import Session
    from utils.emails import send_otp_email
    
    def email_callback(success):
        if success:
            current_app.logger.info(f"OTP email sent successfully to {session.get('password_reset_email')}")
        else:
            current_app.logger.error(f"Failed to send OTP email to {session.get('password_reset_email')}")
    
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        
        # Validate email format
        if not email or "@" not in email:
            flash("Please enter a valid email address.", "error")
            return render_template("auth/forgot_password.html")
        
        # Find user by email
        db = Session()
        try:
            user = db.query(User).filter(func.lower(User.email) == func.lower(email)).first()
            if not user:
                flash("No account found with that email address.", "error")
                return render_template("auth/forgot_password.html")
        
            # Generate a random 8-character alphanumeric OTP
            otp = ''.join(secrets.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789') for _ in range(8))
            
            # Store OTP and expiry time temporarily (in a real app, you'd use a cache like Redis)
            # For now, I'll store it in the session, but this is not ideal for production
            session['password_reset_otp'] = otp
            session['password_reset_email'] = email
            session['password_reset_expiry'] = (datetime.utcnow() + timedelta(minutes=10)).isoformat()
            session['password_reset_user_id'] = user.id  # Store user ID for verification
            
            # Send email with OTP asynchronously
            send_otp_email(email, user.username, otp, callback=email_callback)
            
            flash("An OTP has been sent to your email address. Please check your inbox.", "success")
            return redirect(url_for("auth.reset_password"))
        
        finally:
            db.close()
    
    # GET request
    return render_template("auth/forgot_password.html")


@auth_bp.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    """
    Route to handle password reset with OTP verification.
    """
    from datetime import datetime
    from models import Session
    
    if request.method == "POST":
        otp = request.form.get("otp", "").strip()
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")
        
        # Validate inputs
        if not otp or not new_password or not confirm_password:
            flash("Please fill in all fields.", "error")
            return render_template("auth/reset_password.html")
        
        if new_password != confirm_password:
            flash("Passwords do not match.", "error")
            return render_template("auth/reset_password.html")
        
        if len(new_password) < 8:
            flash("Password must be at least 8 characters long.", "error")
            return render_template("auth/reset_password.html")
        
        # Verify OTP from session
        session_otp = session.get('password_reset_otp')
        session_email = session.get('password_reset_email')
        session_expiry = session.get('password_reset_expiry')
        session_user_id = session.get('password_reset_user_id')
        
        if not all([session_otp, session_email, session_expiry, session_user_id]):
            flash("Invalid or expired OTP. Please request a new one.", "error")
            return redirect(url_for("auth.forgot_password"))
        
        # Check if OTP has expired
        expiry_time = datetime.fromisoformat(session_expiry)
        if datetime.utcnow() > expiry_time:
            flash("OTP has expired. Please request a new one.", "error")
            # Clear session values
            session.pop('password_reset_otp', None)
            session.pop('password_reset_email', None)
            session.pop('password_reset_expiry', None)
            session.pop('password_reset_user_id', None)
            return redirect(url_for("auth.forgot_password"))
        
        # Check if OTP matches
        if otp != session_otp:
            flash("Invalid OTP. Please try again.", "error")
            return render_template("auth/reset_password.html")
        
        # Update user's password
        db = Session()
        try:
            user = db.query(User).get(session_user_id)
            if not user:
                flash("User not found.", "error")
                return redirect(url_for("auth.forgot_password"))
            
            # Verify the email still matches
            if user.email.lower() != session_email.lower():
                flash("Email verification failed. Please request a new OTP.", "error")
                return redirect(url_for("auth.forgot_password"))
            
            # Update password
            user.password_hash = hash_password(new_password)
            db.commit()
            
            # Clear session values
            session.pop('password_reset_otp', None)
            session.pop('password_reset_email', None)
            session.pop('password_reset_expiry', None)
            session.pop('password_reset_user_id', None)
            
            # Log the password change
            auth_logger.info(f"Password reset successful - User: {user.username}, IP: {get_client_ip()}")
            
            flash("Your password has been successfully reset. You can now log in.", "success")
            return redirect(url_for("auth.login"))
        
        finally:
            db.close()
    
    # GET request
    return render_template("auth/reset_password.html")
