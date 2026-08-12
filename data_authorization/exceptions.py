"""Domain exceptions for project authorization management."""


class ProjectAuthorizationError(ValueError):
    """Base error for invalid or unauthorized project grant operations."""


class ProjectGrantValidationError(ProjectAuthorizationError):
    """Raised when a role-scope grant is structurally invalid."""


class ProjectGrantPermissionDenied(ProjectAuthorizationError):
    """Raised when the actor cannot manage the requested project scope."""
