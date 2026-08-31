"""Non-authorization location helpers retained for legacy UI callers."""

from __future__ import annotations

from flask import request

from models import LabUnit, User


CROSS_HOSPITAL_OPERATIONS = {"grading", "arbitration", "research", "training"}


def is_cross_hospital_operation(operation: str) -> bool:
    """Return a UI hint; this function never grants data access."""
    return operation in CROSS_HOSPITAL_OPERATIONS


def get_user_lab_units_in_hospital(
    user_id: int,
    hospital_id: int | None = None,
    db=None,
) -> set[int]:
    """Return assigned Lab Units, optionally narrowed to one hospital."""
    close_session = False
    if db is None:
        from db_transaction_manager import get_db_session

        db = get_db_session().__enter__()
        close_session = True
    try:
        user = db.get(User, user_id)
        if user is None:
            return set()
        if user.has_role("admin") and hospital_id is None:
            return {lab.id for lab in user.lab_units}
        target_hospital_id = hospital_id or user.hospital_id
        if target_hospital_id is None:
            return set()
        return {
            lab.id for lab in user.lab_units
            if lab.hospital_id == target_hospital_id
        }
    finally:
        if close_session:
            db.close()


def validate_lab_unit_hospital_match(
    user_id: int,
    lab_unit_id: int,
    db=None,
) -> bool:
    """Validate location consistency only; callers still authorize separately."""
    close_session = False
    if db is None:
        from db_transaction_manager import get_db_session

        db = get_db_session().__enter__()
        close_session = True
    try:
        user = db.get(User, user_id)
        if user is None:
            raise ValueError(f"User {user_id} not found")
        if user.has_role("admin"):
            return True
        if user.hospital_id is None:
            raise ValueError(f"User {user_id} has no hospital assignment")
        lab_unit = db.get(LabUnit, lab_unit_id)
        return bool(lab_unit and lab_unit.hospital_id == user.hospital_id)
    finally:
        if close_session:
            db.close()


def determine_scoping_context() -> str:
    """Return a presentation hint inferred from the current request."""
    try:
        if request.args.get("context") == "grading":
            return "grading"
        referrer = request.referrer or ""
        if "/grade/" in referrer or "/grading/" in referrer:
            return "grading"
    except RuntimeError:
        pass
    return "upload"


__all__ = [
    "CROSS_HOSPITAL_OPERATIONS",
    "is_cross_hospital_operation",
    "get_user_lab_units_in_hospital",
    "validate_lab_unit_hospital_match",
    "determine_scoping_context",
]
