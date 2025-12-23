"""Logging configuration helpers for the Fundus Image Manager."""
from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Dict, List

from flask import Flask, request


class RequestContextFilter(logging.Filter):
    """Populate request context fields on log records when available."""

    def filter(self, record: logging.LogRecord) -> bool:  # type: ignore[override]
        record.url = "-"
        record.method = "-"
        try:
            record.url = request.url  # type: ignore[attr-defined]
            record.method = request.method  # type: ignore[attr-defined]
        except Exception:
            pass
        return True


def _make_handler(
    filename: str,
    level: int,
    formatter: logging.Formatter,
    *,
    filters: List[logging.Filter] | None = None,
    log_dir: Path,
    max_bytes: int,
    backup_count: int,
) -> logging.Handler:
    handler = RotatingFileHandler(
        log_dir / filename,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
        delay=True,
    )
    handler.setLevel(level)
    handler.setFormatter(formatter)
    for flt in filters or []:
        handler.addFilter(flt)
    return handler


def _configure_logger(
    name: str,
    level: int,
    handler: logging.Handler,
    *,
    extra_handlers: List[logging.Handler] | None = None,
) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False
    for existing in list(logger.handlers):
        logger.removeHandler(existing)
        try:
            existing.close()
        except Exception:
            pass
    logger.addHandler(handler)
    for extra in extra_handlers or []:
        logger.addHandler(extra)
    return logger


def configure_logging(app: Flask) -> Dict[str, logging.Logger]:
    """Configure application loggers and attach them to the Flask app."""
    log_root_setting = app.config.get("LOG_DIR") or os.getenv("LOG_DIR")
    log_dir = Path(log_root_setting or (Path(__file__).resolve().parent.parent / "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)

    debug_mode = bool(app.debug or app.config.get("ENABLE_DEBUG_LOGGING", False))
    log_max_bytes = int(app.config.get("LOG_MAX_BYTES", 2 * 1024 * 1024))
    log_backup_count = int(app.config.get("LOG_BACKUP_COUNT", 5))

    base_format = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s %(message)s")
    detailed_format = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s %(filename)s:%(lineno)d %(message)s"
    )
    http_error_format = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s url=%(url)s %(message)s")

    request_filter = RequestContextFilter()

    http_error_handler = _make_handler(
        "http_error.log",
        logging.WARNING,
        http_error_format,
        filters=[request_filter],
        log_dir=log_dir,
        max_bytes=log_max_bytes,
        backup_count=log_backup_count,
    )
    runtime_error_handler = _make_handler(
        "runtime_error.log",
        logging.ERROR,
        detailed_format,
        log_dir=log_dir,
        max_bytes=log_max_bytes,
        backup_count=log_backup_count,
    )
    grades_handler = _make_handler("grades.log", logging.INFO, base_format, log_dir=log_dir, max_bytes=log_max_bytes, backup_count=log_backup_count)
    pregraded_processing_handler = _make_handler("pregraded_processing.log", logging.INFO, base_format, log_dir=log_dir, max_bytes=log_max_bytes, backup_count=log_backup_count)
    auth_handler = _make_handler("auth.log", logging.INFO, base_format, log_dir=log_dir, max_bytes=log_max_bytes, backup_count=log_backup_count)
    editing_handler = _make_handler("editing.log", logging.INFO, base_format, log_dir=log_dir, max_bytes=log_max_bytes, backup_count=log_backup_count)
    consensus_handler = _make_handler("consensus.log", logging.INFO, base_format, log_dir=log_dir, max_bytes=log_max_bytes, backup_count=log_backup_count)
    email_success_handler = _make_handler("email_success.log", logging.INFO, base_format, log_dir=log_dir, max_bytes=log_max_bytes, backup_count=log_backup_count)
    email_error_handler = _make_handler("email_error.log", logging.ERROR, detailed_format, log_dir=log_dir, max_bytes=log_max_bytes, backup_count=log_backup_count)
    app_handler = _make_handler("app.log", logging.INFO, base_format, log_dir=log_dir, max_bytes=log_max_bytes, backup_count=log_backup_count)
    flask_limiter_handler = _make_handler("flask_limiter.log", logging.INFO, base_format, log_dir=log_dir, max_bytes=log_max_bytes, backup_count=log_backup_count)
    intra_rater_debug_handler = _make_handler("intra_rater_debug.log", logging.INFO, base_format, log_dir=log_dir, max_bytes=log_max_bytes, backup_count=log_backup_count)
    sqlalchemy_failure_handler = _make_handler("sqlalchemy_failure.log", logging.ERROR, detailed_format, log_dir=log_dir, max_bytes=log_max_bytes, backup_count=log_backup_count)
    flash_handler = _make_handler("flash_messages.log", logging.INFO, base_format, log_dir=log_dir, max_bytes=log_max_bytes, backup_count=log_backup_count)
    materialized_view_handler = _make_handler("materialized_view.log", logging.INFO, base_format, log_dir=log_dir, max_bytes=log_max_bytes, backup_count=log_backup_count)
    thumbnail_maintenance_handler = _make_handler("thumbnail_maintenance.log", logging.INFO, base_format, log_dir=log_dir, max_bytes=log_max_bytes, backup_count=log_backup_count)
    startup_env_handler = _make_handler("startup_env_error.log", logging.INFO, detailed_format, log_dir=log_dir, max_bytes=log_max_bytes, backup_count=log_backup_count)
    db_query_handler = _make_handler("db_query.log", logging.INFO, detailed_format, log_dir=log_dir, max_bytes=log_max_bytes, backup_count=log_backup_count)

    debug_handler = None
    console_handler = None
    if debug_mode:
        debug_handler = _make_handler("debug.log", logging.DEBUG, detailed_format, log_dir=log_dir, max_bytes=log_max_bytes, backup_count=log_backup_count)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(detailed_format)

    http_error_logger = _configure_logger("http_error", logging.WARNING, http_error_handler)
    runtime_error_logger = _configure_logger("runtime_error", logging.ERROR, runtime_error_handler)
    grades_logger = _configure_logger("grades", logging.INFO, grades_handler)
    pregraded_processing_logger = _configure_logger("pregraded_processing", logging.INFO, pregraded_processing_handler)
    auth_logger = _configure_logger("auth", logging.INFO, auth_handler)
    editing_logger = _configure_logger("editing", logging.INFO, editing_handler)
    consensus_logger = _configure_logger("consensus", logging.INFO, consensus_handler)
    email_success_logger = _configure_logger("email_success", logging.INFO, email_success_handler)
    email_error_logger = _configure_logger("email_error", logging.ERROR, email_error_handler)
    rate_limit_logger = _configure_logger("rate_limit", logging.INFO, app_handler)
    flask_limiter_logger = _configure_logger("flask-limiter", logging.INFO, flask_limiter_handler)
    intra_rater_debug_logger = _configure_logger("intra_rater_debug", logging.INFO, intra_rater_debug_handler)
    sqlalchemy_failure_logger = _configure_logger("sqlalchemy.failure", logging.ERROR, sqlalchemy_failure_handler)
    flash_logger = _configure_logger("flash.messages", logging.INFO, flash_handler)
    materialized_view_logger = _configure_logger("materialized_view", logging.INFO, materialized_view_handler)
    thumbnail_maintenance_logger = _configure_logger("thumbnail_maintenance", logging.INFO, thumbnail_maintenance_handler)
    startup_env_logger = _configure_logger("startup_env", logging.INFO, startup_env_handler)
    db_query_logger = _configure_logger("db_query", logging.INFO, db_query_handler)

    if app.config.get("EMAIL_DEBUG_LOGGING"):
        email_debug_handler = _make_handler("email_debug.log", logging.DEBUG, detailed_format, log_dir=log_dir, max_bytes=log_max_bytes, backup_count=log_backup_count)
        _configure_logger("email_debug", logging.DEBUG, email_debug_handler)
    else:
        email_debug_logger = logging.getLogger("email_debug")
        for existing in list(email_debug_logger.handlers):
            email_debug_logger.removeHandler(existing)
            try:
                existing.close()
            except Exception:
                pass
        email_debug_logger.handlers = []

    extra_app_handlers: List[logging.Handler] = []
    if debug_handler is not None:
        debug_logger = _configure_logger(
            "debug",
            logging.DEBUG,
            debug_handler,
            extra_handlers=[console_handler] if console_handler else None,
        )
        extra_app_handlers.append(debug_handler)
        if console_handler:
            extra_app_handlers.append(console_handler)
    else:
        debug_logger = _configure_logger("debug", logging.INFO, app_handler)

    app_logger = _configure_logger(
        "app",
        logging.DEBUG if debug_mode else logging.INFO,
        app_handler,
        extra_handlers=extra_app_handlers,
    )

    # Mirror handlers onto app.logger
    app.logger.handlers = []
    app.logger.setLevel(app_logger.level)
    for handler in app_logger.handlers:
        app.logger.addHandler(handler)
    app.logger.propagate = False

    grades_logger.info("Grades logger initialized at %s", str(log_dir / "grades.log"))
    pregraded_processing_logger.info("Pregraded processing logger initialized at %s", str(log_dir / "pregraded_processing.log"))
    auth_logger.info("Auth logger initialized at %s", str(log_dir / "auth.log"))
    editing_logger.info("Editing logger initialized at %s", str(log_dir / "editing.log"))
    consensus_logger.info("Consensus logger initialized at %s", str(log_dir / "consensus.log"))
    email_success_logger.info("Email success logger initialized at %s", str(log_dir / "email_success.log"))
    email_error_logger.info("Email error logger initialized at %s", str(log_dir / "email_error.log"))
    runtime_error_logger.info("Runtime error logger initialized at %s", str(log_dir / "runtime_error.log"))
    flask_limiter_logger.info("Flask-Limiter logger initialized at %s", str(log_dir / "flask_limiter.log"))
    intra_rater_debug_logger.info("Intra-rater debug logger initialized at %s", str(log_dir / "intra_rater_debug.log"))
    sqlalchemy_failure_logger.info("SQLAlchemy failure logger ready at %s", str(log_dir / "sqlalchemy_failure.log"))
    flash_logger.info("Flash message logger initialized at %s", str(log_dir / "flash_messages.log"))
    materialized_view_logger.info("Materialized view logger initialized at %s", str(log_dir / "materialized_view.log"))
    thumbnail_maintenance_logger.info("Thumbnail maintenance logger initialized at %s", str(log_dir / "thumbnail_maintenance.log"))
    startup_env_logger.info("Startup environment logger initialized at %s", str(log_dir / "startup_env_error.log"))
    db_query_logger.info("DB query logger initialized at %s", str(log_dir / "db_query.log"))

    return {
        "http_error": http_error_logger,
        "runtime_error": runtime_error_logger,
        "grades": grades_logger,
        "pregraded_processing": pregraded_processing_logger,
        "auth": auth_logger,
        "editing": editing_logger,
        "consensus": consensus_logger,
        "email_success": email_success_logger,
        "email_error": email_error_logger,
        "rate_limit": rate_limit_logger,
        "flask_limiter": flask_limiter_logger,
        "intra_rater_debug": intra_rater_debug_logger,
        "sqlalchemy_failure": sqlalchemy_failure_logger,
        "flash": flash_logger,
        "materialized_view": materialized_view_logger,
        "thumbnail_maintenance": thumbnail_maintenance_logger,
        "startup_env": startup_env_logger,
        "db_query": db_query_logger,
        "app": app_logger,
        "debug": debug_logger,
    }
