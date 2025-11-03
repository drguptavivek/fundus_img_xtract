#!/usr/bin/env python3
"""
Provision a standard set of test users for local development.

The script ensures the Community Ophthalmology lab unit exists under
'RPC AIIMS' and then creates or updates users with predictable
credentials, roles, and grading permissions. Passwords are intentionally
shared across accounts to simplify testing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence
import sys
from pathlib import Path

# Add the project root directory to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from auth.roles import DEFAULT_ROLES, ensure_roles
from auth.security import hash_password
from models import (
    Session,
    User,
    Role,
    Hospital,
    LabUnit,
    Disease,
    UserDiseaseUnitRole,
)


DEFAULT_PASSWORD = "Vivek@2026"
TARGET_HOSPITAL = "RPC AIIMS"
TARGET_LAB_UNIT = "Community Ophthalmology"


@dataclass(frozen=True)
class SlotPermission:
    """Represents a grading slot assignment for a single disease."""

    disease_name: str
    slot: str  # resident | resident2 | arbitrator


@dataclass(frozen=True)
class TestUserConfig:
    """Configuration holder for a test user."""

    username: str
    full_name: str
    role_names: Sequence[str]
    slot_permissions: Sequence[SlotPermission] = ()
    all_lab_units: bool = False  # If True, assign to all lab units of the hospital


TEST_USER_CONFIGS: List[TestUserConfig] = [
    TestUserConfig(
        username="testadmin",
        full_name="Development Administrator",
        role_names=("admin",),
    ),
    TestUserConfig(
        username="test2ComophArbit",
        full_name="Test Comoph Arbitrator",
        role_names=("ophthalmologist",),
        slot_permissions=(
            SlotPermission("Glaucoma", "arbitrator"),
            SlotPermission("DR", "arbitrator"),
        ),
    ),
    TestUserConfig(
        username="test2ComophFac",
        full_name="Test Comoph Resident2",
        role_names=("ophthalmologist",),
        slot_permissions=(
            SlotPermission("Glaucoma", "resident2"),
            SlotPermission("DR", "resident2"),
        ),
    ),
    TestUserConfig(
        username="test2ComophResident",
        full_name="Test Comoph Resident",
        role_names=("ophthalmologist",),
        slot_permissions=(
            SlotPermission("Glaucoma", "resident"),
            SlotPermission("DR", "resident"),
        ),
    ),
    TestUserConfig(
        username="testUploader",
        full_name="Test Community Ophthalmology Uploader",
        role_names=("fileUploader",),
    ),
    TestUserConfig(
        username="testOptometrist",
        full_name="Test Community Ophthalmology Optometrist",
        role_names=("optometrist",),
    ),
    TestUserConfig(
        username="testManager",
        full_name="Test Community Ophthalmology Manager",
        role_names=("data_manager",),
    ),
    TestUserConfig(
        username="admin",
        full_name="System Administrator",
        role_names=("admin",),
        all_lab_units=True,  # Assign to all lab units of hospital ID 1
    ),
]


def _get_or_raise_hospital(db: OrmSession) -> Hospital:
    hospital = db.execute(
        select(Hospital).where(Hospital.name == TARGET_HOSPITAL)
    ).scalar_one_or_none()
    if not hospital:
        raise RuntimeError(f"Hospital '{TARGET_HOSPITAL}' not found. Run initial setup first.")
    return hospital


def _get_or_raise_lab_unit(db: OrmSession, hospital_id: int) -> LabUnit:
    lab_unit = db.execute(
        select(LabUnit).where(
            LabUnit.name == TARGET_LAB_UNIT,
            LabUnit.hospital_id == hospital_id,
        )
    ).scalar_one_or_none()
    if not lab_unit:
        raise RuntimeError(
            f"Lab unit '{TARGET_LAB_UNIT}' under hospital '{TARGET_HOSPITAL}' not found."
        )
    return lab_unit


def _load_diseases(db: OrmSession, names: Iterable[str]) -> dict[str, Disease]:
    rows = db.execute(select(Disease).where(Disease.name.in_(list(set(names))))).scalars().all()
    disease_map = {d.name: d for d in rows}
    missing = set(names) - set(disease_map)
    if missing:
        raise RuntimeError(f"Missing diseases required for test users: {', '.join(sorted(missing))}")
    return disease_map


def _load_roles(db: OrmSession, names: Iterable[str]) -> dict[str, Role]:
    ensure_roles(db, DEFAULT_ROLES)
    rows = db.execute(select(Role).where(Role.name.in_(list(set(names))))).scalars().all()
    role_map = {r.name: r for r in rows}
    missing = set(names) - set(role_map)
    if missing:
        raise RuntimeError(f"Missing roles required for test users: {', '.join(sorted(missing))}")
    return role_map


def _apply_slot_permissions(
    db: OrmSession,
    user: User,
    lab_unit: LabUnit,
    disease_map: dict[str, Disease],
    permissions: Sequence[SlotPermission],
) -> None:
    """Create UserDiseaseUnitRole rows for the provided permissions."""
    slot_to_flags = {
        "resident": dict(can_grade_resident=True, can_grade_resident2=False, can_arbitrate=False),
        "resident2": dict(can_grade_resident=False, can_grade_resident2=True, can_arbitrate=False),
        "arbitrator": dict(can_grade_resident=False, can_grade_resident2=False, can_arbitrate=True),
    }

    # Remove existing assignments
    existing_roles = db.execute(
        select(UserDiseaseUnitRole).where(UserDiseaseUnitRole.user_id == user.id)
    ).scalars().all()
    for role in existing_roles:
        db.delete(role)

    for permission in permissions:
        flags = slot_to_flags.get(permission.slot)
        if flags is None:
            raise ValueError(f"Unsupported slot '{permission.slot}' for user '{user.username}'.")
        disease = disease_map.get(permission.disease_name)
        if not disease:
            raise RuntimeError(
                f"Disease '{permission.disease_name}' not available when assigning permissions."
            )
        record = UserDiseaseUnitRole(
            user_id=user.id,
            disease_id=disease.id,
            lab_unit_id=lab_unit.id,
            active=True,
            **flags,
        )
        db.add(record)


def add_test_users() -> None:
    """Create or update the full suite of development test users."""
    with Session() as db:
        hospital = _get_or_raise_hospital(db)
        lab_unit = _get_or_raise_lab_unit(db, hospital.id)

        disease_names = {
            permission.disease_name
            for config in TEST_USER_CONFIGS
            for permission in config.slot_permissions
        }
        disease_map = _load_diseases(db, disease_names) if disease_names else {}

        role_names = {role for config in TEST_USER_CONFIGS for role in config.role_names}
        role_map = _load_roles(db, role_names)

        password_hash = hash_password(DEFAULT_PASSWORD)

        for config in TEST_USER_CONFIGS:
            user = db.execute(
                select(User).where(User.username == config.username)
            ).scalar_one_or_none()

            was_created = False
            if user is None:
                user = User(
                    username=config.username,
                    full_name=config.full_name,
                    password_hash=password_hash,
                    is_active=True,
                )
                db.add(user)
                db.flush()
                was_created = True
            else:
                user.full_name = config.full_name
                user.password_hash = password_hash
                user.is_active = True

            # Replace role assignments
            user.roles.clear()
            for role_name in config.role_names:
                role = role_map.get(role_name)
                if role is None:
                    raise RuntimeError(f"Role '{role_name}' missing when configuring '{user.username}'.")
                user.roles.append(role)

            # Ensure lab unit association
            user.lab_units.clear()
            
            if config.all_lab_units:
                # Get all lab units for the hospital
                all_lab_units = db.execute(
                    select(LabUnit).where(LabUnit.hospital_id == hospital.id)
                ).scalars().all()
                
                for lab_unit_item in all_lab_units:
                    user.lab_units.append(lab_unit_item)
                print(f"  Assigned to all {len(all_lab_units)} lab units of hospital '{hospital.name}'")
            else:
                # Assign only to the target lab unit
                user.lab_units.append(lab_unit)

            _apply_slot_permissions(db, user, lab_unit, disease_map, config.slot_permissions)
            db.commit()

            action = "Created" if was_created else "Updated"
            print(f"{action} user '{user.username}' with roles {', '.join(config.role_names)}.")

        print("\nDevelopment test users are ready.")
        print("Shared password for all test users:", DEFAULT_PASSWORD)


if __name__ == "__main__":
    add_test_users()
