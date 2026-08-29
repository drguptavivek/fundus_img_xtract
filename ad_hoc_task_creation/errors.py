from __future__ import annotations


class AdHocTaskCreationError(ValueError):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def invalid(message: str) -> AdHocTaskCreationError:
    return AdHocTaskCreationError(message, status_code=400)


def denied(message: str = "Ad-hoc task creation is not authorized.") -> AdHocTaskCreationError:
    return AdHocTaskCreationError(message, status_code=403)


def conflict(message: str) -> AdHocTaskCreationError:
    return AdHocTaskCreationError(message, status_code=409)
