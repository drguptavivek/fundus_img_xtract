"""Compatibility imports for linked grading graph helpers."""

from grading.workbench.linked_tasks import (  # noqa: F401
    expand_primary_disease_ids,
    get_linked_disease_ids,
    get_primary_disease_id,
    is_primary_disease,
    validate_acyclic,
)

__all__ = [
    "expand_primary_disease_ids",
    "get_linked_disease_ids",
    "get_primary_disease_id",
    "is_primary_disease",
    "validate_acyclic",
]
