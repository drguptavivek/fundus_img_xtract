"""Upload eligibility helpers backed by explicit lab-unit membership."""

from db_transaction_manager import get_db_session
from models import LabUnit, User
from sqlalchemy.orm import selectinload
from upload_profiles.service import explicit_lab_unit_ids, get_user_lab_unit_ids


def get_user_lab_unit_ids_no_admin_override(user_id: int) -> set[int]:
    """Return explicitly assigned lab-unit IDs with no role/admin expansion."""
    with get_db_session() as db:
        return explicit_lab_unit_ids(db, user_id)


def get_user_uploadVerify_eligibility(user_id: int) -> dict:
    """Return hospital/lab-unit upload eligibility for a user."""
    with get_db_session() as db:
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
        lab_units_iterable = (
            db.query(LabUnit).options(selectinload(LabUnit.hospital)).order_by(LabUnit.id).all()
            if is_admin
            else list(user.lab_units or [])
        )

        hospital_map: dict[int, dict] = {}
        for lab_unit in lab_units_iterable:
            hospital = lab_unit.hospital
            if hospital is None:
                continue
            entry = hospital_map.setdefault(
                hospital.id,
                {"hospital_id": hospital.id, "hospital_name": hospital.name, "lab_units": []},
            )
            entry["lab_units"].append({"lab_unit_id": lab_unit.id, "lab_unit_name": lab_unit.name})

        for entry in hospital_map.values():
            entry["lab_units"].sort(key=lambda item: item["lab_unit_id"])

        return {
            "user_id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "hospitals": sorted(hospital_map.values(), key=lambda item: item["hospital_id"]),
        }


__all__ = [
    "get_user_uploadVerify_eligibility",
    "get_user_lab_unit_ids",
    "get_user_lab_unit_ids_no_admin_override",
]
