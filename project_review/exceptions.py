"""Project review domain errors."""


class ProjectReviewError(ValueError):
    """Base project review error."""


class ProjectReviewNotFound(ProjectReviewError):
    """The project does not exist or is outside the user's membership scope."""
