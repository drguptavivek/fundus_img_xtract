"""User impersonation domain service."""

from .service import (
    ImpersonationError,
    ImpersonationResult,
    start_impersonation,
    stop_impersonation,
)

__all__ = [
    "ImpersonationError",
    "ImpersonationResult",
    "start_impersonation",
    "stop_impersonation",
]
