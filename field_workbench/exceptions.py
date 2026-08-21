"""Typed failures for the field surface."""
from __future__ import annotations


class FieldError(Exception):
    code = "field_error"
    status_code = 400

    def __init__(self, message: str, *, code: str | None = None, status_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code


class FieldNotFound(FieldError):
    """Also raised for an unauthorized project, so existence is not leaked."""

    code = "not_found"
    status_code = 404

    def __init__(self, message: str = "Not found.") -> None:
        super().__init__(message)


class FieldAccessDenied(FieldError):
    code = "forbidden"
    status_code = 403

    def __init__(self, message: str = "You do not have access to this resource.") -> None:
        super().__init__(message)


class FieldConflict(FieldError):
    code = "conflict"
    status_code = 409


class FieldThrottled(FieldError):
    code = "rate_limited"
    status_code = 429

    def __init__(self, message: str, *, retry_after: int) -> None:
        super().__init__(message)
        self.retry_after = retry_after
