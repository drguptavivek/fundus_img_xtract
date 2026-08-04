"""Explicit, unsafe web-login bypass for local and test environments."""

from __future__ import annotations

import logging

from flask import Flask, jsonify, request
from flask_login import current_user, login_user
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from db_transaction_manager import transaction_scope
from models import User


LOGIN_DISABLED_USERNAME = "main_admin"

logger = logging.getLogger("auth")


def _load_main_admin() -> User | None:
    with transaction_scope() as db:
        user = (
            db.execute(
                select(User)
                .options(
                    selectinload(User.roles),
                    selectinload(User.lab_units),
                    selectinload(User.hospital),
                )
                .where(
                    User.username == LOGIN_DISABLED_USERNAME,
                    User.is_active.is_(True),
                )
            )
            .scalars()
            .one_or_none()
        )
        if user is not None:
            db.expunge(user)
        return user


def register_login_disabled_override(app: Flask) -> None:
    """Impersonate ``main_admin`` whenever the explicit bypass is enabled."""
    if app.config.get("LOGIN_DISABLED"):
        app.logger.critical(
            "UNSAFE LOGIN_DISABLED override enabled; web requests run as %s",
            LOGIN_DISABLED_USERNAME,
        )

    @app.before_request
    def _apply_login_disabled_identity():
        if not app.config.get("LOGIN_DISABLED"):
            return None

        path = request.path or "/"
        if (
            path.startswith("/static/")
            or path == "/healthz"
            or path == "/mobile"
            or path.startswith("/mobile/")
            or path.startswith("/api/mobile/")
        ):
            return None

        if (
            current_user.is_authenticated
            and getattr(current_user, "username", None) == LOGIN_DISABLED_USERNAME
            and getattr(current_user, "is_active", False)
        ):
            return None

        user = _load_main_admin()
        if user is None:
            logger.critical(
                "LOGIN_DISABLED cannot apply: active user %s was not found",
                LOGIN_DISABLED_USERNAME,
            )
            return jsonify(
                {
                    "error": "login_disabled_identity_unavailable",
                    "message": "LOGIN_DISABLED requires an active main_admin user.",
                }
            ), 503

        login_user(user, remember=False, force=True, fresh=True)
        return None


__all__ = ["LOGIN_DISABLED_USERNAME", "register_login_disabled_override"]
