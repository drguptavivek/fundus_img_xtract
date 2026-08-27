"""Decorators that attach static endpoint metadata without making decisions."""

from __future__ import annotations

from functools import wraps

from authz_v2.core.actions import Action, action_from_name
from authz_v2.flask.contracts import EndpointMode, EndpointPolicy


def authorization_endpoint(
    mode: EndpointMode,
    action: str | Action,
    *,
    resolver: str | None = None,
    enforcement: str = "handler",
):
    """Classify exactly one Flask endpoint for centralized default-deny checks."""
    policy = EndpointPolicy(mode, action_from_name(action), resolver, enforcement)

    def decorate(fn):
        if getattr(fn, "__authz_endpoint_policy__", None) is not None:
            raise ValueError("endpoint already has an authorization classification")

        @wraps(fn)
        def wrapper(*args, **kwargs):
            return fn(*args, **kwargs)

        wrapper.__authz_endpoint_policy__ = policy
        return wrapper

    return decorate
