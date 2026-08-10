"""Compatibility imports for grading workbench revision rules."""

from grading.workbench.revisions import (  # noqa: F401
    REVISION_WINDOW_HOURS,
    check_arbitrator_revision_eligibility,
    check_revision_eligibility_by_task_state,
    is_arbitrator_eligible_for_revision,
    is_arbitrator_revision_allowed,
    is_user_eligible_for_revision,
)

__all__ = [
    "REVISION_WINDOW_HOURS",
    "check_arbitrator_revision_eligibility",
    "check_revision_eligibility_by_task_state",
    "is_arbitrator_eligible_for_revision",
    "is_arbitrator_revision_allowed",
    "is_user_eligible_for_revision",
]
