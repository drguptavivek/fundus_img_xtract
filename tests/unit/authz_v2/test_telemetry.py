import json
import logging
from logging.handlers import WatchedFileHandler
from pathlib import Path

from flask import Flask

from app_init.logging_config import RequestContextFilter, configure_logging
from authz_v2.telemetry.events import AuthorizationEvent
from authz_v2.telemetry.logging import emit_authorization_event
from authz_v2.telemetry.metrics import duration_snapshot, observe_decision_duration


class Capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


def test_operational_event_contains_only_privacy_allowlisted_fields():
    handler = Capture()
    logger = logging.getLogger("test.authorization.capture")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    event = AuthorizationEvent(
        "decision",
        "request-1",
        1,
        "web",
        "fundus_api.authorization_catalogue",
        "admin.system.manage",
        "allow",
        "admin_break_glass",
        True,
        1.25,
    )
    emit_authorization_event(event, logger=logger)
    payload = json.loads(handler.messages[0])
    assert set(payload) == {
        "event",
        "request_id",
        "actor_id",
        "session_kind",
        "endpoint",
        "action",
        "outcome",
        "policy_path",
        "break_glass",
        "duration_ms",
    }
    assert not {"url", "query", "token", "resource_id", "username"} & set(payload)


def test_application_files_have_one_external_rotation_owner(tmp_path):
    app = Flask(__name__)
    app.config["LOG_DIR"] = str(tmp_path)
    loggers = configure_logging(app)
    assert "authorization" in loggers
    for logger in loggers.values():
        for handler in logger.handlers:
            if isinstance(handler, logging.FileHandler):
                assert isinstance(handler, WatchedFileHandler)


def test_decision_duration_metric_has_only_action_cardinality():
    observe_decision_duration("project.view", 0.025)
    count, total = duration_snapshot()["project.view"]
    assert count >= 1
    assert total >= 0.025


def test_request_log_context_never_contains_query_or_credential_values():
    app = Flask(__name__)

    @app.get("/probe")
    def probe():
        return "ok"

    with app.test_request_context("/probe?token=secret"):
        app.url_map.bind("").match("/probe")
        record = logging.LogRecord("test", logging.INFO, __file__, 1, "x", (), None)
        RequestContextFilter().filter(record)
        assert record.endpoint == "probe"
        assert not hasattr(record, "url")

    app_source = (Path(__file__).parents[3] / "app.py").read_text(encoding="utf-8")
    assert "Session cookie value" not in app_source
    assert "Form CSRF token value" not in app_source
    assert "sanitize_log_value(request.url)" not in app_source
