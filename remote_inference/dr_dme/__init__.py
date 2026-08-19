"""Deep domain package for encounter-scoped DR/DME remote inference."""

from .candidates import (
    ALLOWED_PAGE_SIZES,
    MAX_MANUAL_ENCOUNTERS,
    CandidateFilters,
    CandidatePage,
    list_candidates,
    validate_selection_count,
)

__all__ = [
    "ALLOWED_PAGE_SIZES",
    "MAX_MANUAL_ENCOUNTERS",
    "CandidateFilters",
    "CandidatePage",
    "list_candidates",
    "validate_selection_count",
]
