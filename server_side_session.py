"""Server-side session storage backed by the application database."""
from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from flask.sessions import SessionInterface, SessionMixin
from werkzeug.datastructures import CallbackDict

from models import Session as DbSession, FlaskSession


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
        cookie_name = app.config.get("SESSION_COOKIE_NAME", "session")
        session_id = request.cookies.get(cookie_name)
        db = DbSession()
        try:
            if not session_id:
                return self.session_class(session_id=self._generate_sid(), new=True)

            stored = db.get(FlaskSession, session_id)
            if not stored:
                return self.session_class(session_id=self._generate_sid(), new=True)

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
        cookie_name = app.config.get("SESSION_COOKIE_NAME", "session")

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
                )
                db.add(stored)
            else:
                stored.data = payload
                stored.expiry = expires
                if user_id_value is not None:
                    stored.user_id = user_id_value
                if stored.started_at is None:
                    stored.started_at = self._now()
            db.commit()
        finally:
            db.close()

        response.set_cookie(
            cookie_name,
            session.session_id,
            expires=expires,
            httponly=app.config.get("SESSION_COOKIE_HTTPONLY", True),
            secure=app.config.get("SESSION_COOKIE_SECURE", False),
            samesite=app.config.get("SESSION_COOKIE_SAMESITE", "Lax"),
            path=self.get_cookie_path(app),
            domain=self.get_cookie_domain(app),
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
