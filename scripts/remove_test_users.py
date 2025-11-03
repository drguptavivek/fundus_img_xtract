#!/usr/bin/env python3
"""
Remove the standard set of test users created for local development.

This script removes all test users created by add_test_users.py,
including their associated roles, permissions, and lab unit assignments.
"""

from __future__ import annotations

from typing import List
import sys
from pathlib import Path

# Add the project root directory to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from models import (
    Session,
    User,
    UserDiseaseUnitRole,
)

# List of test usernames to remove (matching those in add_test_users.py)
TEST_USERNAMES: List[str] = [
    "testadmin",
    "test2ComophArbit",
    "test2ComophFac",
    "test2ComophResident",
    "testUploader",
    "testOptometrist",
    "testManager",
]


def remove_test_users() -> None:
    """Remove all test users and their associated data."""
    with Session() as db:
        # Find all test users
        test_users = db.execute(
            select(User).where(User.username.in_(TEST_USERNAMES))
        ).scalars().all()
        
        if not test_users:
            print("No test users found to remove.")
            return
        
        # Remove each test user and their associated data
        for user in test_users:
            username = user.username
            
            # Remove UserDiseaseUnitRole entries for this user
            user_disease_roles = db.execute(
                select(UserDiseaseUnitRole).where(UserDiseaseUnitRole.user_id == user.id)
            ).scalars().all()
            
            for role in user_disease_roles:
                db.delete(role)
            
            # Remove the user (this will also remove role assignments due to cascade)
            db.delete(user)
            
            print(f"Removed test user '{username}' and all associated data.")
        
        db.commit()
        print(f"\nSuccessfully removed {len(test_users)} test users.")


if __name__ == "__main__":
    remove_test_users()