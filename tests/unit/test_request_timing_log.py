from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from flask import Flask
from flask_login import LoginManager

from app import _parse_utc_instant, _register_request_timing


def _app(until):
    app = Flask(__name__)
    app.config["REQUEST_TIMING_LOG_UNTIL"] = until
    LoginManager(app).user_loader(lambda _id: None)
    app.add_url_rule("/ping", "ping", lambda: "pong")
    return app


def _timing_lines(app, caplog):
    timing_logger = logging.getLogger("test_request_timing")
    _register_request_timing(app, logging.getLogger("test_http_error"), timing_logger)
    with caplog.at_level(logging.INFO, logger="test_request_timing"):
        app.test_client().get("/ping")
    return [r.getMessage() for r in caplog.records if r.name == "test_request_timing"]


def test_logs_every_request_while_window_is_open(caplog):
    lines = _timing_lines(_app(datetime.now(timezone.utc) + timedelta(hours=1)), caplog)

    assert len(lines) == 1
    assert " GET /ping 200 duration=" in lines[0]
    assert "bytes=4 user=- endpoint=ping" in lines[0]


def test_silent_once_window_has_passed(caplog):
    assert _timing_lines(_app(datetime.now(timezone.utc) - timedelta(seconds=1)), caplog) == []


def test_silent_when_unset(caplog):
    assert _timing_lines(_app(None), caplog) == []


def test_parse_utc_instant():
    assert _parse_utc_instant("2026-10-08T06:00:00Z") == datetime(2026, 10, 8, 6, tzinfo=timezone.utc)
    assert _parse_utc_instant("2026-10-08T06:00:00") == datetime(2026, 10, 8, 6, tzinfo=timezone.utc)
    assert _parse_utc_instant("") is None
    assert _parse_utc_instant(None) is None
    assert _parse_utc_instant("not-a-date") is None
