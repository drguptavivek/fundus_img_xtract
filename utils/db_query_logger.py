"""Debug-only SQLAlchemy query logging for slow and frequent queries."""
from __future__ import annotations

import inspect
import logging
import threading
import time
from dataclasses import dataclass
from typing import Dict, Optional

from flask import has_request_context, request
from sqlalchemy import event


@dataclass
class QueryStats:
    count: int = 0
    total_ms: float = 0.0
    max_ms: float = 0.0
    last_seen: float = 0.0
    last_route: str = "-"
    last_endpoint: str = "-"
    last_caller: str = "-"


class QueryLogger:
    def __init__(
        self,
        logger: logging.Logger,
        slow_threshold_ms: int,
        window_seconds: int,
        top_n: int,
        flush_interval_seconds: int,
    ) -> None:
        self._logger = logger
        self._slow_threshold_ms = slow_threshold_ms
        self._window_seconds = window_seconds
        self._top_n = top_n
        self._flush_interval_seconds = flush_interval_seconds
        self._stats: Dict[str, QueryStats] = {}
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
        if len(normalized) > 500:
            normalized = normalized[:500] + "..."

        route = "-"
        endpoint = "-"
        if has_request_context():
            route = request.path or "-"
            endpoint = request.endpoint or "-"

        caller = _find_caller()
        now = time.time()

        if duration_ms >= self._slow_threshold_ms:
            self._logger.warning(
                "Slow query %dms route=%s endpoint=%s caller=%s sql=%s",
                int(duration_ms),
                route,
                endpoint,
                caller,
                normalized,
            )

        with self._lock:
            stats = self._stats.get(normalized)
            if stats is None:
                stats = QueryStats()
                self._stats[normalized] = stats
            stats.count += 1
            stats.total_ms += duration_ms
            stats.max_ms = max(stats.max_ms, duration_ms)
            stats.last_seen = now
            stats.last_route = route
            stats.last_endpoint = endpoint
            stats.last_caller = caller

    def _flush_loop(self) -> None:
        while not self._stop_event.is_set():
            self._stop_event.wait(self._flush_interval_seconds)
            if self._stop_event.is_set():
                break
            self.flush()

    def flush(self) -> None:
        cutoff = time.time() - self._window_seconds
        with self._lock:
            active = {
                sql: stats for sql, stats in self._stats.items() if stats.last_seen >= cutoff
            }
            stale_keys = [sql for sql, stats in self._stats.items() if stats.last_seen < cutoff]
            for sql in stale_keys:
                del self._stats[sql]

        if not active:
            return

        top_items = sorted(active.items(), key=lambda item: item[1].count, reverse=True)[: self._top_n]
        lines = []
        for sql, stats in top_items:
            avg_ms = stats.total_ms / stats.count if stats.count else 0.0
            lines.append(
                "count=%d avg_ms=%.1f max_ms=%.1f route=%s endpoint=%s caller=%s sql=%s"
                % (
                    stats.count,
                    avg_ms,
                    stats.max_ms,
                    stats.last_route,
                    stats.last_endpoint,
                    stats.last_caller,
                    sql,
                )
            )

        self._logger.info(
            "Top %d frequent queries (window=%ds)\n%s",
            self._top_n,
            self._window_seconds,
            "\n".join(lines),
        )


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
    window_seconds: int = 24 * 60 * 60,
    top_n: int = 20,
    flush_interval_seconds: int = 30,
) -> Optional[QueryLogger]:
    enabled = bool(app.debug or app.config.get("DB_QUERY_LOGGING", False))
    if not enabled:
        return None

    logger = logging.getLogger("db_query")
    query_logger = QueryLogger(
        logger=logger,
        slow_threshold_ms=slow_threshold_ms,
        window_seconds=window_seconds,
        top_n=top_n,
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
