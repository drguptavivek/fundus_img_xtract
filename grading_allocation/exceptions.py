"""Typed grading-allocation domain errors."""

from typing import Any


class GradingAllocationError(ValueError):
    status_code = 400
    code = "grading_allocation_error"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class AllocationNotFoundError(GradingAllocationError):
    status_code = 404
    code = "grading_allocation_not_found"


class AllocationForbiddenError(GradingAllocationError):
    status_code = 403
    code = "grading_allocation_forbidden"


class AllocationConflictError(GradingAllocationError):
    status_code = 409
    code = "grading_allocation_conflict"


class AllocationContextError(GradingAllocationError):
    code = "grading_allocation_context_invalid"
