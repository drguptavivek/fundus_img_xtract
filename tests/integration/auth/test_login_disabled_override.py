"""Behavioral coverage for the explicit login-disabled test override."""

import pytest
from flask import Flask, jsonify
from flask_login import current_user

from auth.decorators import reauth_required
from auth.roles import roles_required
from auth.security import hash_password
from models import Role, User


def _create_main_admin(db_session, *, active: bool = True) -> User:
    admin_role = db_session.query(Role).filter_by(name="admin").one()
    user = User(
        username="main_admin",
        password_hash=hash_password("unused-login-disabled-password"),
        is_active=active,
        is_master_admin=True,
        roles=[admin_role],
    )
    db_session.add(user)
    db_session.flush()
    return user


def test_login_disabled_environment_value_is_loaded(monkeypatch):
    from app import _configure_base_settings

    monkeypatch.setenv("LOGIN_DISABLED", "true")
    configured_app = Flask("login-disabled-config-test")

    _configure_base_settings(configured_app)

    assert configured_app.config["LOGIN_DISABLED"] is True


def test_login_disabled_is_rejected_in_production(monkeypatch):
    from app import _configure_base_settings

    monkeypatch.setenv("LOGIN_DISABLED", "true")
    monkeypatch.setenv("FLASK_ENV", "production")
    configured_app = Flask("login-disabled-production-test")

    with pytest.raises(RuntimeError, match="LOGIN_DISABLED.*development"):
        _configure_base_settings(configured_app)


def test_login_disabled_request_uses_main_admin_and_bypasses_role_guard(app, db_session):
    main_admin = _create_main_admin(db_session)
    app.config["LOGIN_DISABLED"] = True

    @app.get("/_test/login-disabled/identity")
    @roles_required("role-main-admin-does-not-have")
    @reauth_required()
    def login_disabled_identity():
        return jsonify({"user_id": current_user.id, "username": current_user.username})

    response = app.test_client().get("/_test/login-disabled/identity")

    assert response.status_code == 200
    assert response.get_json() == {
        "user_id": main_admin.id,
        "username": "main_admin",
    }


def test_login_protection_remains_enabled_by_default(app):
    @app.get("/_test/login-disabled/default-off")
    @roles_required("admin")
    def protected_when_override_is_off():
        return jsonify({"ok": True})

    response = app.test_client().get("/_test/login-disabled/default-off")

    assert app.config["LOGIN_DISABLED"] is False
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


def test_login_disabled_fails_closed_when_main_admin_is_unavailable(app):
    app.config["LOGIN_DISABLED"] = True

    @app.get("/_test/login-disabled/missing-identity")
    def missing_login_disabled_identity():
        return jsonify({"ok": True})

    response = app.test_client().get("/_test/login-disabled/missing-identity")

    assert response.status_code == 503
    assert response.get_json() == {
        "error": "login_disabled_identity_unavailable",
        "message": "LOGIN_DISABLED requires an active main_admin user.",
    }


def test_login_disabled_fails_closed_when_main_admin_is_inactive(app, db_session):
    _create_main_admin(db_session, active=False)
    app.config["LOGIN_DISABLED"] = True

    @app.get("/_test/login-disabled/inactive-identity")
    def inactive_login_disabled_identity():
        return jsonify({"ok": True})

    response = app.test_client().get("/_test/login-disabled/inactive-identity")

    assert response.status_code == 503
    assert response.get_json()["error"] == "login_disabled_identity_unavailable"
