"""Stable vocabulary for project grading allocation."""

from enum import StrEnum


class AllocationScope(StrEnum):
    DISEASE_IMAGE = "disease_image"
    DISEASE_ENCOUNTER = "disease_encounter"
    ENCOUNTER_SET_UNIFIED = "encounter_set_unified"


class AllocationCapacity(StrEnum):
    RESIDENT = "resident"
    ARBITRATOR = "arbitrator"


def capacity_for_role_slot(role_slot: str) -> AllocationCapacity | None:
    """Map sequential grading slots onto the two assignable capacities."""
    if role_slot in {"resident", "resident2"}:
        return AllocationCapacity.RESIDENT
    if role_slot == "arbitrator":
        return AllocationCapacity.ARBITRATOR
    return None
