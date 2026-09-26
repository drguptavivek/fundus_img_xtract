"""Typed failures for the project data sync workflow."""
from __future__ import annotations


class ProjectSyncError(Exception):
    """Base error; ``status_code`` and ``code`` map directly onto API responses."""

    status_code = 400
    code = "project_sync_error"

    def __init__(self, message: str, *, code: str | None = None, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code


class ProjectSyncDisabled(ProjectSyncError):
    status_code = 503
    code = "project_sync_disabled"

    def __init__(self, message: str = "Project data sync is disabled on this server."):
        super().__init__(message)


class ProjectSyncValidationError(ProjectSyncError):
    status_code = 400
    code = "validation_error"


class ProjectSyncPermissionDenied(ProjectSyncError):
    status_code = 403
    code = "forbidden"


class ProjectSyncNotFound(ProjectSyncError):
    status_code = 404
    code = "not_found"


class ProjectSyncConflict(ProjectSyncError):
    status_code = 409
    code = "conflict"


class ProjectSyncAuthError(ProjectSyncError):
    """Credential rejected. The message never says which check failed."""

    status_code = 401
    code = "invalid_sync_credential"

    def __init__(self, message: str = "Invalid or inactive sync credential."):
        super().__init__(message)
