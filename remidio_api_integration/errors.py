"""Typed errors for the Remidio API integration boundary."""

from __future__ import annotations


class RemidioIntegrationError(RuntimeError):
    """Base class for integration failures safe to translate into API responses."""

    status_code = 400


class RemidioConfigError(RemidioIntegrationError):
    """Raised when a local connection or route configuration is invalid."""

    status_code = 400


class RemidioValidationError(RemidioIntegrationError):
    """Raised when Remidio returns a response shape we cannot safely process."""

    status_code = 502


class RemidioRemoteError(RemidioIntegrationError):
    """Raised when the remote Remidio API rejects or fails a request."""

    status_code = 502

    def __init__(
        self,
        message: str,
        *,
        remote_status_code: int | None = None,
        response_snapshot: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.remote_status_code = remote_status_code
        self.response_snapshot = response_snapshot or {}
