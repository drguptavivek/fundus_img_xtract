#!/usr/bin/env python3
"""
Script to create a test admin user with username 'Test' and password 'test@123'
"""

import sys
from pathlib import Path
import os

# Add the project root to the path
file_path = Path(__file__).resolve()
project_root = file_path.parent.parent
sys.path.insert(0, str(project_root))

try:
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import select
    from sqlalchemy.exc import SQLAlchemyError
    from models import engine, User, Role
    from auth.security import hash_password
    from auth.roles import ensure_roles, DEFAULT_ROLES
    from utils.timezone_choices import DEFAULT_TIMEZONE
except ModuleNotFoundError as e:
    print(f"Error importing modules: {e}", file=sys.stderr)
    sys.exit(1)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

def create_test_admin():
    """Create test admin user with predefined credentials"""
    username = "Test"
    password = "test@123"
    
    with SessionLocal() as db:
        # Ensure default roles exist
        ensure_roles(db, DEFAULT_ROLES)
        
        # Check if user already exists
        existing_user = db.execute(
            select(User).where(User.username.ilike(username))
        ).scalar_one_or_none()
        
        if existing_user:
            print(f"User '{username}' already exists.")
            # Check if they already have admin role
            admin_role = db.execute(
                select(Role).where(Role.name == "admin")
            ).scalar_one_or_none()
            
            if admin_role and admin_role in existing_user.roles:
                print(f"User '{username}' already has admin role.")
                return existing_user
            else:
                # Add admin role to existing user
                if admin_role:
                    existing_user.roles.append(admin_role)
                    db.add(existing_user)
                    db.commit()
                    print(f"Added admin role to existing user '{username}'.")
                    return existing_user
        else:
            # Create new user
            new_user = User(
                username=username,
                password_hash=hash_password(password),
                timezone=os.getenv("DEFAULT_DISPLAY_TIMEZONE", DEFAULT_TIMEZONE),
            )
            db.add(new_user)
            db.flush()  # Get the user ID
            
            # Add admin role
            admin_role = db.execute(
                select(Role).where(Role.name == "admin")
            ).scalar_one_or_none()
            
            if admin_role:
                new_user.roles.append(admin_role)
                db.add(new_user)
                db.commit()
                print(f"Created new admin user '{username}' with password '{password}'.")
                return new_user
            else:
                print("Error: Admin role not found in database.", file=sys.stderr)
                db.rollback()
                return None

if __name__ == "__main__":
    try:
        user = create_test_admin()
        if user:
            print("Test admin user created successfully!")
            print("Username: Test")
            print("Password: test@123")
        else:
            print("Failed to create test admin user.", file=sys.stderr)
            sys.exit(1)
    except SQLAlchemyError as e:
        print(f"Database error: {e}", file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(3)