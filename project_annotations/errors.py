class AnnotationPolicyError(Exception):
    """Base project annotation policy error."""


class AnnotationPolicyNotFound(AnnotationPolicyError):
    pass


class AnnotationPolicyValidationError(AnnotationPolicyError):
    pass


class AnnotationPolicyAccessDenied(AnnotationPolicyError):
    pass


class AnnotationPolicyConflictError(AnnotationPolicyError):
    """Raised when an administrator submits a stale policy revision."""
