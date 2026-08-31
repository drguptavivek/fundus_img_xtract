"""Typed authorization failures."""

from __future__ import annotations

from werkzeug.exceptions import Forbidden


class AuthorizationDenied(Forbidden):
    """A fail-closed authorization denial suitable for Flask and services."""

    def __init__(self, reason: str = "access_denied") -> None:
        self.reason = reason
        super().__init__(description="You do not have permission to access this resource.")
