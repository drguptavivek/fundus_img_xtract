"""Helpers for resolving user upload eligibility."""
from __future__ import annotations

from typing import Any, Dict, List, Set

from sqlalchemy.orm import selectinload

from models import Session, User, LabUnit


def get_user_uploadVerify_eligibility(user_id: int) -> Dict[str, Any]:
    """Return upload eligibility details for the given user.

    The payload contains the user identity and a hospital → lab unit mapping
    describing where the user is permitted to upload images. Data is read from
    the ``user_lab_units`` association table via the ``User.lab_units``
    relationship.

    Args:
        user_id: The primary key of the user.

    Returns:
        A dictionary containing ``user_id``, ``username``, ``full_name``, and a
        ``hospitals`` collection. When the user does not exist or has no
        associated lab units the mapping will contain an empty ``hospitals``
        list.
    """
    db = Session()
    try:
        user = (
            db.query(User)
            .options(
                selectinload(User.lab_units).selectinload(LabUnit.hospital),
                selectinload(User.roles),
            )
            .filter(User.id == user_id)
            .one_or_none()
        )
        if user is None:
            return {}

        is_admin = any(role.name == "admin" for role in (user.roles or []))

        hospital_map: Dict[int, Dict[str, Any]] = {}
        if is_admin:
            lab_units_iterable = (
                db.query(LabUnit)
                .options(selectinload(LabUnit.hospital))
                .order_by(LabUnit.id)
                .all()
            )
        else:
            lab_units_iterable = list(user.lab_units or [])

        for lab_unit in lab_units_iterable:
            hospital = lab_unit.hospital
            if hospital is None:
                continue

            hosp_entry = hospital_map.setdefault(
                hospital.id,
                {
                    "hospital_id": hospital.id,
                    "hospital_name": hospital.name,
                    "lab_units": [],
                },
            )

            hosp_entry["lab_units"].append(
                {
                    "lab_unit_id": lab_unit.id,
                    "lab_unit_name": lab_unit.name,
                }
            )

        # Sort lab units for determinism
        for entry in hospital_map.values():
            entry["lab_units"].sort(key=lambda item: item["lab_unit_id"])

        hospitals: List[Dict[str, Any]] = sorted(
            hospital_map.values(), key=lambda item: item["hospital_id"]
        )

        return {
            "user_id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "hospitals": hospitals,
        }
    finally:
        db.close()


def get_user_lab_unit_ids(user_id: int) -> Set[int]:
    """Return the set of lab unit IDs the user is allowed to access."""
    db = Session()
    try:
        user = (
            db.query(User)
            .options(
                selectinload(User.lab_units),
                selectinload(User.roles),
            )
            .filter(User.id == user_id)
            .one_or_none()
        )
        if not user:
            return set()

        if any(role.name == "admin" for role in (user.roles or [])):
            all_ids = db.query(LabUnit.id).all()
            return {row[0] for row in all_ids}

        if not user.lab_units:
            return set()
        return {lu.id for lu in user.lab_units}
    finally:
        db.close()


def get_user_lab_unit_ids_no_admin_override(user_id: int) -> Set[int]:
    """Return the set of lab unit IDs the user is explicitly assigned to, without admin override.
    
    This function only returns lab units that are directly associated with the user,
    regardless of their admin status. This is useful when you want to filter
    based on the current user's actual assignments rather than giving admins
    access to everything.
    """
    db = Session()
    try:
        user = (
            db.query(User)
            .options(
                selectinload(User.lab_units),
                selectinload(User.roles),
            )
            .filter(User.id == user_id)
            .one_or_none()
        )
        if not user:
            return set()

        if not user.lab_units:
            return set()
        return {lu.id for lu in user.lab_units}
    finally:
        db.close()


__all__ = ["get_user_uploadVerify_eligibility", "get_user_lab_unit_ids", "get_user_lab_unit_ids_no_admin_override"]
