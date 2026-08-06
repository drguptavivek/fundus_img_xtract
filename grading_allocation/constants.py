"""Stable vocabulary for project grading allocation."""

from enum import StrEnum


class AllocationScope(StrEnum):
    DISEASE_IMAGE = "disease_image"
    DISEASE_ENCOUNTER = "disease_encounter"
    ENCOUNTER_SET_UNIFIED = "encounter_set_unified"


class AllocationCapacity(StrEnum):
    RESIDENT = "resident"
    ARBITRATOR = "arbitrator"


class AllocationTaskFamily(StrEnum):
    ENCOUNTER_SET_SCOPED = "encounter_set_scoped"
    IMAGE_SCOPED_ENCOUNTER_SET = "image_scoped_encounter_set"
    IMAGE_WISE_NON_SET = "image_wise_non_set"


def task_family_for_scope(scope: AllocationScope) -> AllocationTaskFamily:
    if scope == AllocationScope.ENCOUNTER_SET_UNIFIED:
        return AllocationTaskFamily.ENCOUNTER_SET_SCOPED
    if scope == AllocationScope.DISEASE_ENCOUNTER:
        return AllocationTaskFamily.IMAGE_SCOPED_ENCOUNTER_SET
    return AllocationTaskFamily.IMAGE_WISE_NON_SET


def capacity_for_role_slot(role_slot: str) -> AllocationCapacity | None:
    """Map sequential grading slots onto the two assignable capacities."""
    if role_slot in {"resident", "resident2"}:
        return AllocationCapacity.RESIDENT
    if role_slot == "arbitrator":
        return AllocationCapacity.ARBITRATOR
    return None
