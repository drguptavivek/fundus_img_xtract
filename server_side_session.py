"""Server-side session storage backed by the application database."""
from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from flask.sessions import SessionInterface, SessionMixin
from werkzeug.datastructures import CallbackDict
from sqlalchemy import select, and_

from models import Session as DbSession, FlaskSession

# Logger for session operations
session_logger = logging.getLogger('session')


class DatabaseSession(CallbackDict, SessionMixin):
    def __init__(self, initial=None, session_id: Optional[str] = None, new: bool = False):
        def on_update(self):
            self.modified = True

        super().__init__(initial or {}, on_update)
        self.session_id = session_id
        self.new = new
        self.modified = False


class DatabaseSessionInterface(SessionInterface):
    serializer = json
    session_class = DatabaseSession

    def __init__(self, key_length: int = 64):
        self.key_length = key_length
        self._current_request = None

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def _generate_sid(self) -> str:
        return secrets.token_hex(self.key_length // 2)

    def _get_permanent_lifetime(self, app) -> timedelta:
        lifetime = app.permanent_session_lifetime
        if not isinstance(lifetime, timedelta):
            lifetime = timedelta(seconds=int(lifetime))
        return lifetime

    @staticmethod
    def _ensure_utc(dt: datetime) -> datetime:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    def open_session(self, app, request):
        # Skip session handling for static files to improve performance and avoid database issues
        if request.path and request.path.startswith('/static/'):
            return None
        if request.path in ("/healthz", "/healthz/"):
            return None

        # Get client IP address
        def get_client_ip():
            # Check for IP in headers (common for reverse proxies)
            if request.headers.getlist("X-Forwarded-For"):
                return request.headers.getlist("X-Forwarded-For")[0]
            elif request.headers.getlist("X-Real-IP"):
                return request.headers.getlist("X-Real-IP")[0]
            else:
                return request.remote_addr

        client_ip = get_client_ip()

        # Store the current request for later use in save_session
        self._current_request = request

        cookie_name = app.config.get("SESSION_COOKIE_NAME", "session")
        session_id = request.cookies.get(cookie_name)

        db = DbSession()
        try:
            if not session_id:
                new_sid = self._generate_sid()
                return self.session_class(session_id=new_sid, new=True)

            stored = db.get(FlaskSession, session_id)
            if not stored:
                new_sid = self._generate_sid()
                return self.session_class(session_id=new_sid, new=True)
            
            updated = False
            stored.expiry = self._ensure_utc(stored.expiry)
            if stored.started_at is None:
                stored.started_at = stored.expiry
                updated = True

            now = self._now()
            if stored.ended_at is not None or stored.expiry <= now:
                if stored.ended_at is None:
                    stored.ended_at = now
                    stored.expiry = now
                    stored.data = "{}"
                    updated = True
                if updated:
                    db.commit()
                return self.session_class(session_id=self._generate_sid(), new=True)

            if updated:
                db.commit()

            data = self.serializer.loads(stored.data)
            return self.session_class(data, session_id=session_id)
        finally:
            db.close()

    def save_session(self, app, session, response):
        # Skip session handling for static files
        if session is None:
            return

        cookie_name = app.config.get("SESSION_COOKIE_NAME", "session")
        session_id = getattr(session, "session_id", None)

        # Get client IP address using stored request
        def get_client_ip():
            request = self._current_request
            if request.headers.getlist("X-Forwarded-For"):
                return request.headers.getlist("X-Forwarded-For")[0]
            elif request.headers.getlist("X-Real-IP"):
                return request.headers.getlist("X-Real-IP")[0]
            else:
                return request.remote_addr

        client_ip = get_client_ip()

        # If the session is empty, stamp it as ended and remove the browser cookie
        if not session:
            session_id = getattr(session, "session_id", None)
            if session_id:
                db = DbSession()
                try:
                    stored = db.get(FlaskSession, session_id)
                    if stored:
                        now = self._now()
                        stored.data = "{}"
                        stored.expiry = now
                        if stored.started_at is None:
                            stored.started_at = now
                        if stored.ended_at is None:
                            stored.ended_at = now
                        # Update IP address on session end
                        stored.ip_address = client_ip
                        db.commit()
                finally:
                    db.close()
            response.delete_cookie(
                cookie_name,
                path=self.get_cookie_path(app),
                domain=self.get_cookie_domain(app),
            )
            return

        if not getattr(session, "session_id", None):
            session.session_id = self._generate_sid()

        expires = self.get_expiration_time(app, session)
        if expires is None:
            expires = self._now() + self._get_permanent_lifetime(app)
        expires = self._ensure_utc(expires)

        db = DbSession()
        try:
            stored = db.get(FlaskSession, session.session_id)
            payload_dict = dict(session)
            payload_dict['_ip_address'] = client_ip  # Add IP to session data
            payload = self.serializer.dumps(payload_dict)
            raw_user_id = payload_dict.get("_user_id")
            try:
                user_id_value = int(raw_user_id) if raw_user_id is not None else None
            except (TypeError, ValueError):
                user_id_value = None
            if stored is None:
                stored = FlaskSession(
                    session_id=session.session_id,
                    data=payload,
                    expiry=expires,
                    user_id=user_id_value,
                    started_at=self._now(),
                    ip_address=client_ip,
                )
                db.add(stored)
            else:
                stored.data = payload
                stored.expiry = expires
                stored.ip_address = client_ip  # Update IP address
                if user_id_value is not None:
                    stored.user_id = user_id_value
                if stored.started_at is None:
                    stored.started_at = self._now()
            db.commit()

            # SECURITY: Enforce concurrent session limit on user login
            # This prevents session abuse by limiting active sessions per user
            if user_id_value is not None:
                enforce_concurrent_session_limit(session.session_id, user_id_value)

                # SECURITY: Session rotation on fresh login
                # Invalidate all other sessions when user logs in from new device
                # This prevents session fixation attacks (CWE-384)
                is_fresh_login = payload_dict.get("_fresh_login", False)
                if is_fresh_login:
                    invalidated = invalidate_all_other_sessions(session.session_id, user_id_value)
                    if invalidated > 0:
                        session_logger.info(
                            "Session rotation on login - UserID: %s, CurrentSession: %s, Invalidated: %d",
                            user_id_value,
                            session.session_id,
                            invalidated,
                        )
                    # Clear the flag so we don't invalidate on every save
                    payload_dict.pop("_fresh_login", None)
                    stored.data = self.serializer.dumps(payload_dict)
                    db.commit()
        finally:
            db.close()

        lifetime_seconds = int(self._get_permanent_lifetime(app).total_seconds())
        cookie_settings = {
            # Use max_age so browser uses its own clock instead of server time for expiry
            'max_age': lifetime_seconds,
            'httponly': app.config.get("SESSION_COOKIE_HTTPONLY", True),
            'secure': app.config.get("SESSION_COOKIE_SECURE", False),
            'samesite': app.config.get("SESSION_COOKIE_SAMESITE", "Lax"),
            'path': self.get_cookie_path(app),
            'domain': self.get_cookie_domain(app),
        }
        
        response.set_cookie(
            cookie_name,
            session.session_id,
            **cookie_settings
        )


def mark_session_ended(session_id: str, user_id: int | None = None) -> None:
    """Record the end of a session outside the normal save lifecycle."""
    if not session_id:
        return

    db = DbSession()
    try:
        stored = db.get(FlaskSession, session_id)
        if stored is None:
            return

        authoritative_user_id = user_id
        if authoritative_user_id is None:
            if stored.user_id is not None:
                authoritative_user_id = stored.user_id
            else:
                try:
                    payload = DatabaseSessionInterface.serializer.loads(stored.data)
                    raw_user_id = payload.get("_user_id")
                    if raw_user_id is not None:
                        authoritative_user_id = int(raw_user_id)
                except Exception:
                    authoritative_user_id = None

        now = datetime.now(timezone.utc)
        stored.expiry = now
        if stored.started_at is None:
            stored.started_at = now
        if stored.ended_at is None or stored.ended_at < now:
            stored.ended_at = now
        if authoritative_user_id is not None:
            stored.user_id = authoritative_user_id
        stored.data = "{}"
        db.commit()
    finally:
        db.close()


# Maximum number of concurrent active sessions per user
MAX_CONCURRENT_SESSIONS = 3


def invalidate_all_other_sessions(current_session_id: str, user_id: int) -> int:
    """
    Invalidate all sessions for a user except the current one.

    This is used for "log out all other sessions" functionality and
    as part of session rotation on login to prevent session fixation.

    Args:
        current_session_id: The session ID to keep active
        user_id: The user ID whose other sessions should be invalidated

    Returns:
        The number of sessions that were invalidated

    Security:
        - Prevents session fixation by invalidating old sessions
        - Allows users to log out from all other devices
        - Logs all invalidations with reason
    """
    if not current_session_id or not user_id:
        return 0

    db = DbSession()
    try:
        now = datetime.now(timezone.utc)

        # Find all active sessions for this user except the current one
        other_sessions = db.execute(
            select(FlaskSession).where(
                and_(
                    FlaskSession.user_id == user_id,
                    FlaskSession.session_id != current_session_id,
                    FlaskSession.ended_at.is_(None),
                    FlaskSession.expiry > now
                )
            )
        ).scalars().all()

        invalidated_count = 0
        for sess in other_sessions:
            sess.ended_at = now
            sess.expiry = now
            sess.data = "{}"
            invalidated_count += 1

            # Log session invalidation
            session_logger.info(
                "Session invalidated for user - SessionID: %s, UserID: %s, Reason: other_sessions_invalidation",
                sess.session_id,
                user_id,
            )

        if invalidated_count > 0:
            db.commit()
            session_logger.info(
                "Invalidated %d other sessions for user - UserID: %s, CurrentSession: %s",
                invalidated_count,
                user_id,
                current_session_id,
            )

        return invalidated_count
    finally:
        db.close()


def enforce_concurrent_session_limit(session_id: str, user_id: int) -> int:
    """
    Enforce the maximum concurrent session limit per user.

    If a user has more than MAX_CONCURRENT_SESSIONS active sessions,
    invalidate the oldest sessions (by started_at) to maintain the limit.

    Args:
        session_id: The current/new session ID
        user_id: The user ID whose sessions should be limited

    Returns:
        The number of sessions that were invalidated

    Security:
        - Prevents session abuse by limiting concurrent sessions
        - Oldest sessions are invalidated first
        - Logs all enforcement actions
    """
    if not session_id or not user_id:
        return 0

    db = DbSession()
    try:
        now = datetime.now(timezone.utc)

        # Count active sessions for this user
        active_sessions = db.execute(
            select(FlaskSession).where(
                and_(
                    FlaskSession.user_id == user_id,
                    FlaskSession.ended_at.is_(None),
                    FlaskSession.expiry > now
                )
            ).order_by(FlaskSession.started_at.asc())
        ).scalars().all()

        active_count = len(active_sessions)

        # If within limit, nothing to do
        if active_count <= MAX_CONCURRENT_SESSIONS:
            return 0

        # Need to invalidate oldest sessions (first N sessions where N = active_count - MAX)
        to_invalidate = active_count - MAX_CONCURRENT_SESSIONS
        invalidated_count = 0

        for sess in active_sessions[:to_invalidate]:
            sess.ended_at = now
            sess.expiry = now
            sess.data = "{}"
            invalidated_count += 1

            # Log session invalidation
            session_logger.info(
                "Session invalidated due to concurrent limit - SessionID: %s, UserID: %s, StartedAt: %s",
                sess.session_id,
                user_id,
                sess.started_at,
            )

        if invalidated_count > 0:
            db.commit()
            session_logger.info(
                "Enforced concurrent session limit for user - UserID: %s, Invalidated: %d, Limit: %d",
                user_id,
                invalidated_count,
                MAX_CONCURRENT_SESSIONS,
            )

        return invalidated_count
    finally:
        db.close()


def invalidate_all_user_sessions(user_id: int) -> int:
    """
    Invalidate ALL sessions for a user (including current).

    This is used for forced logout (e.g., password change, role change,
    account lock, admin action).

    Args:
        user_id: The user ID whose sessions should be invalidated

    Returns:
        The number of sessions that were invalidated
    """
    if not user_id:
        return 0

    db = DbSession()
    try:
        now = datetime.now(timezone.utc)

        # Find all active sessions for this user
        active_sessions = db.execute(
            select(FlaskSession).where(
                and_(
                    FlaskSession.user_id == user_id,
                    FlaskSession.ended_at.is_(None),
                )
            )
        ).scalars().all()

        invalidated_count = 0
        for sess in active_sessions:
            sess.ended_at = now
            sess.expiry = now
            sess.data = "{}"
            invalidated_count += 1

            # Log session invalidation
            session_logger.info(
                "Session invalidated for user - SessionID: %s, UserID: %s, Reason: all_sessions_invalidated",
                sess.session_id,
                user_id,
            )

        if invalidated_count > 0:
            db.commit()
            session_logger.info(
                "Invalidated all %d sessions for user - UserID: %s",
                invalidated_count,
                user_id,
            )

        return invalidated_count
    finally:
        db.close()
