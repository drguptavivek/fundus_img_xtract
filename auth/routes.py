# auth/routes.py
from __future__ import annotations
from datetime import timedelta
import time
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
                # Start sliding inactivity window
                session.permanent = True  # enable cookie expiration control
                session["last_active"] = int(time.time())
                session.modified = True

                # Optional: rotate session / set remember as needed
                return redirect(url_for("homepage"))

            # Failure path
            _record_attempt(db, username, ip, success=False)

            # Re-check windows after this failure to possibly trigger locks
            if _recent_failed_by_username(db, username) >= MAX_FAILS_PER_USERNAME and user:
                until = _lock_user(db, user)
                return render_template("auth/login.html",
                                       error=f"User locked due to repeated failures until {until.isoformat()}.")
            if _recent_failed_by_ip(db, ip) >= MAX_FAILS_PER_IP:
                until = _lock_ip(db, ip)
                return render_template("auth/login.html",
                                       error=f"This IP is locked due to repeated failures until {until.isoformat()}.")

            # Generic error (avoid username enumeration)
            return render_template("auth/login.html", error="Invalid username or password.")

        # GET
        return render_template("auth/login.html")

@auth_bp.route("/logout", methods=["POST", "GET"])
@login_required
def logout():
    logout_user()
    flash("You’ve been signed out.", "info")
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
