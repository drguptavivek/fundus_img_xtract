"""Dependency-free low-cardinality counters for authorization health."""

from __future__ import annotations

from collections import Counter
from threading import Lock

_counts: Counter[tuple[str, str, str]] = Counter()
_duration_count: Counter[str] = Counter()
_duration_sum: Counter[str] = Counter()
_lock = Lock()


def increment(metric: str, *, action: str = "", outcome: str = "") -> None:
    if metric not in {
        "authz_decisions_total",
        "authz_break_glass_total",
        "authz_unclassified_endpoint_total",
        "authz_audit_write_failures_total",
    }:
        raise ValueError("unsupported authorization metric")
    with _lock:
        _counts[(metric, action, outcome)] += 1


def snapshot() -> dict[tuple[str, str, str], int]:
    with _lock:
        return dict(_counts)


def observe_decision_duration(action: str, seconds: float) -> None:
    """Record a low-cardinality decision timing without resource labels."""
    if seconds < 0:
        raise ValueError("authorization duration cannot be negative")
    with _lock:
        _duration_count[action] += 1
        _duration_sum[action] += seconds


def duration_snapshot() -> dict[str, tuple[int, float]]:
    with _lock:
        return {
            action: (_duration_count[action], float(_duration_sum[action]))
            for action in _duration_count
        }
