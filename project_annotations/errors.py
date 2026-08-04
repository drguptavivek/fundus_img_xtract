class AnnotationPolicyError(Exception):
    """Base project annotation policy error."""


class AnnotationPolicyNotFound(AnnotationPolicyError):
    pass


class AnnotationPolicyValidationError(AnnotationPolicyError):
    pass


class AnnotationPolicyAccessDenied(AnnotationPolicyError):
    pass
