"""Helpers for resolving user upload eligibility."""
from __future__ import annotations

from typing import Any, Dict, List

from sqlalchemy.orm import selectinload

from models import Session, User, LabUnit


def get_user_upload_eligibility(user_id: int) -> Dict[str, Any]:
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
            .options(selectinload(User.lab_units).selectinload(LabUnit.hospital))
            .filter(User.id == user_id)
            .one_or_none()
        )
        if user is None:
            return {}

        hospital_map: Dict[int, Dict[str, Any]] = {}
        for lab_unit in user.lab_units or []:
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


__all__ = ["get_user_upload_eligibility"]
