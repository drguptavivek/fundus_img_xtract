"""Structured logging that emits only the authorization privacy allowlist."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict

from authz_v2.telemetry.events import AuthorizationEvent


def emit_authorization_event(
    event: AuthorizationEvent, *, logger: logging.Logger | None = None
) -> None:
    target = logger or logging.getLogger("authorization")
    target.info(json.dumps(asdict(event), separators=(",", ":"), sort_keys=True))
