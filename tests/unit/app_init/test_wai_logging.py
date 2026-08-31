from __future__ import annotations

import logging

from flask import Flask

from app_init.logging_config import configure_logging


def test_configure_logging_creates_dedicated_wai_log(tmp_path):
    app = Flask(__name__)
    app.config["LOG_DIR"] = str(tmp_path)

    loggers = configure_logging(app)
    wai_logger = loggers["wai"]
    wai_logger.error("provider_failure provider=madhunetrai http_status=502")
    for handler in wai_logger.handlers:
        handler.flush()

    assert wai_logger.name == "wai"
    assert wai_logger.propagate is False
    assert "provider_failure provider=madhunetrai http_status=502" in (
        tmp_path / "wai.log"
    ).read_text(encoding="utf-8")
