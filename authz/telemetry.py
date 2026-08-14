"""Non-disclosing operational telemetry for central authorization decisions.

This module deliberately records no resource identifier, media source type,
storage location, or policy denial reason.  Operators can monitor allow/deny
volume and cache health without learning whether a probed patient-media UUID
exists.
"""

from __future__ import annotations

import logging

from authz.types import GrantSource


_LOGGER = logging.getLogger("authorization")


def record_authorization_decision(
    *,
    action: str,
    allowed: bool,
    actor_id: int | None,
    grant_source: GrantSource | None = None,
    cache_hit: bool = False,
) -> None:
    """Record a resource-blind authorization outcome for operations monitoring.

    Resource identifiers and denial reasons are intentionally not accepted by
    this interface.  Grant evidence is emitted only for successful decisions.
    """
    outcome = "allow" if allowed else "deny"
    fields = [
        "event=authorization_decision",
        f"outcome={outcome}",
        f"action={action}",
        f"actor_id={actor_id if actor_id is not None else 'anonymous'}",
    ]
    if allowed:
        fields.append(f"cache_hit={str(bool(cache_hit)).lower()}")
        if grant_source is not None:
            fields.append(f"grant_source={grant_source.value}")
    _LOGGER.info(" ".join(fields))


def record_authorization_cache_error(*, operation: str, error: Exception) -> None:
    """Record a cache failure without values, keys, tokens, or exception text."""
    _LOGGER.warning(
        "event=authorization_cache_error operation=%s error_type=%s",
        operation,
        type(error).__name__,
    )
