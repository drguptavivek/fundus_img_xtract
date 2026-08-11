from __future__ import annotations


class RemidioEncounterMigrationError(Exception):
    """Validated error returned by the Remidio encounter migration module."""

    def __init__(self, message: str, *, status_code: int = 400, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details or {}
