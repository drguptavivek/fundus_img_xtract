"""Debug-only SQLAlchemy query logging with buffered flush."""
from __future__ import annotations

import inspect
import logging
import threading
import time
from typing import List, Optional

from flask import has_request_context, request
from sqlalchemy import event


class QueryLogger:
    def __init__(
        self,
        logger: logging.Logger,
        slow_logger: logging.Logger,
        slow_threshold_ms: int,
        flush_interval_seconds: int,
        max_sql_length: int = 500,
    ) -> None:
        self._logger = logger
        self._slow_logger = slow_logger
        self._slow_threshold_ms = slow_threshold_ms
        self._flush_interval_seconds = flush_interval_seconds
        self._max_sql_length = max_sql_length
        self._buffer: List[str] = []
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._flush_loop, daemon=True)

    def start(self) -> None:
        if not self._thread.is_alive():
            self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def record(self, statement: str, duration_ms: float) -> None:
        normalized = " ".join(statement.split())
        if len(normalized) > self._max_sql_length:
            normalized = normalized[: self._max_sql_length] + "..."

        route = "-"
        endpoint = "-"
        if has_request_context():
            route = request.path or "-"
            endpoint = request.endpoint or "-"

        caller = _find_caller()
        now = time.time()

        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now))
        line = (
            "ts=%s | ms=%.1f | route=%s | endpoint=%s | caller=%s | sql=%s"
            % (timestamp, duration_ms, route, endpoint, caller, normalized)
        )

        if duration_ms >= self._slow_threshold_ms:
            self._slow_logger.warning(line)

        with self._lock:
            self._buffer.append(line)

    def _flush_loop(self) -> None:
        while not self._stop_event.is_set():
            self._stop_event.wait(self._flush_interval_seconds)
            if self._stop_event.is_set():
                break
            self.flush()

    def flush(self) -> None:
        with self._lock:
            pending = self._buffer
            self._buffer = []

        for line in pending:
            self._logger.info(line)


def _find_caller() -> str:
    for frame_info in inspect.stack()[2:]:
        filename = frame_info.filename
        if "/sqlalchemy/" in filename.replace("\\", "/"):
            continue
        if "/utils/db_query_logger.py" in filename.replace("\\", "/"):
            continue
        return f"{filename}:{frame_info.lineno}"
    return "unknown"


def init_db_query_logger(
    app,
    engine,
    *,
    slow_threshold_ms: int = 200,
    flush_interval_seconds: int = 60,
) -> Optional[QueryLogger]:
    enabled = bool(app.debug or app.config.get("DB_QUERY_LOGGING", False))
    if not enabled:
        return None

    logger = logging.getLogger("db_query")
    slow_logger = logging.getLogger("db_query_slow")
    query_logger = QueryLogger(
        logger=logger,
        slow_logger=slow_logger,
        slow_threshold_ms=slow_threshold_ms,
        flush_interval_seconds=flush_interval_seconds,
    )
    query_logger.start()

    @event.listens_for(engine, "before_cursor_execute")
    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):  # type: ignore[unused-argument]
        context._query_start_time = time.time()

    @event.listens_for(engine, "after_cursor_execute")
    def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):  # type: ignore[unused-argument]
        start_time = getattr(context, "_query_start_time", None)
        if start_time is None:
            return
        duration_ms = (time.time() - start_time) * 1000.0
        query_logger.record(statement, duration_ms)

    return query_logger
