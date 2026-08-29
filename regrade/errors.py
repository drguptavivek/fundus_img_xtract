from __future__ import annotations


class RegradeError(Exception):
    def __init__(
        self,
        message: str,
        *,
        code: str = "regrade_error",
        status_code: int = 400,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}


def invalid(message: str, *, code: str = "invalid_request") -> RegradeError:
    return RegradeError(message, code=code, status_code=400)


def denied(message: str = "Regrade authorization denied.") -> RegradeError:
    return RegradeError(message, code="authorization_denied", status_code=403)


def not_found(message: str = "Regrade task not found.") -> RegradeError:
    return RegradeError(message, code="not_found", status_code=404)


def conflict(message: str, *, code: str = "conflict") -> RegradeError:
    return RegradeError(message, code=code, status_code=409)
