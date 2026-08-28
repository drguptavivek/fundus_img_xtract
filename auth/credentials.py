"""Markers for routes that authenticate with an exact non-session credential."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar


F = TypeVar("F", bound=Callable)


def credential_authenticated(view: F) -> F:
    """Mark a view that validates its own token/OTP credential fail closed."""

    setattr(view, "_credential_auth_applied", True)
    return view
