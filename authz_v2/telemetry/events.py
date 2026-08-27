"""Low-cardinality structured authorization event contracts."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AuthorizationEvent:
    event: str
    request_id: str | None
    actor_id: int | None
    session_kind: str
    endpoint: str
    action: str
    outcome: str
    policy_path: str | None
    break_glass: bool
    duration_ms: float

    def __post_init__(self) -> None:
        if self.outcome not in {"allow", "deny", "error"}:
            raise ValueError("invalid authorization telemetry outcome")
