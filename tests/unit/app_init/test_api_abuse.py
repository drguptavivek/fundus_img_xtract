from unittest.mock import Mock
from contextlib import nullcontext

import pytest
import redis
from flask import Flask

from app_init.api_abuse import BAN_SECONDS, FAILURE_LIMIT, WINDOW_SECONDS, register_api_abuse_guard


@pytest.fixture
def guarded_app(monkeypatch):
    import db_transaction_manager
    from security_incidents import service
    monkeypatch.setattr(db_transaction_manager, "transaction_scope", lambda: nullcontext(object()))
    monkeypatch.setattr(service, "record_ip_ban", Mock())
    app = Flask(__name__)
    app.config["API_ABUSE_GUARD_ENABLED"] = True
    backend = Mock()
    backend.ttl.return_value = -2
    backend.eval.return_value = 0
    app.extensions["api_abuse_backend"] = backend
    register_api_abuse_guard(app)
    app.add_url_rule("/api/denied", endpoint="denied", view_func=lambda: ("denied", 401))
    app.add_url_rule("/api/ok", endpoint="ok", view_func=lambda: "ok")
    app.add_url_rule("/healthz", endpoint="healthz", view_func=lambda: "healthy")
    return app, backend


def test_ban_blocks_before_api_executes_and_exposes_retry(guarded_app):
    app, backend = guarded_app
    backend.ttl.return_value = BAN_SECONDS
    response = app.test_client().get("/api/ok")
    assert response.status_code == 429
    assert response.json["error"] == "ip_temporarily_banned"
    assert response.headers["Retry-After"] == str(BAN_SECONDS)
    backend.eval.assert_not_called()
    assert app.test_client().get("/healthz").status_code == 200


def test_denials_accumulate_across_paths_and_headers_cannot_select_bucket(guarded_app):
    app, backend = guarded_app
    client = app.test_client()
    assert client.get("/api/denied", headers={"X-Forwarded-For": "1.2.3.4"}).status_code == 401
    first = backend.eval.call_args
    assert first.args[5:8] == (WINDOW_SECONDS, FAILURE_LIMIT, BAN_SECONDS)
    assert client.get("/api/missing", headers={"X-Forwarded-For": "9.8.7.6"}).status_code == 404
    assert backend.eval.call_args.args[2:4] == first.args[2:4]
    backend.eval.reset_mock()
    assert client.get("/api/ok").status_code == 200
    backend.eval.assert_not_called()


def test_backend_failure_is_closed(guarded_app):
    app, backend = guarded_app
    backend.ttl.side_effect = redis.ConnectionError("offline")
    response = app.test_client().get("/api/ok")
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "60"


def test_ban_and_denial_are_logged_without_authorization(guarded_app, caplog, monkeypatch):
    from app_init.api_abuse import logger
    monkeypatch.setattr(logger, "handlers", [caplog.handler])
    app, backend = guarded_app
    backend.eval.return_value = 1
    response = app.test_client().get("/api/denied", headers={"Authorization": "Bearer TOP-SECRET"})
    assert response.status_code == 401
    assert "API IP ban imposed" in caplog.text
    assert "TOP-SECRET" not in caplog.text
