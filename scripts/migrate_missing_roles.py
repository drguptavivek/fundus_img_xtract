#!/usr/bin/env python3
"""
Migration script to add any missing roles to the database.
This script ensures that all roles used in the application are present in the database.

Usage:
  python scripts/migrate_missing_roles.py
  python scripts/migrate_missing_roles.py --dry-run
"""

import argparse
import sys
from pathlib import Path

# Ensure project root is importable when running this script directly
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy.orm import sessionmaker
from models import engine, Role
from auth.roles import DEFAULT_ROLES

def migrate_missing_roles(dry_run: bool = False) -> None:
    """Add any missing roles to the database."""
    print("Checking for missing roles in database...")
    
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with SessionLocal() as db:
        # Get existing roles from database
        existing_roles = {r.name for r in db.query(Role).all()}
        print(f"Existing roles in database: {sorted(existing_roles)}")
        
        # Identify missing roles
        missing_roles = [role for role in DEFAULT_ROLES if role not in existing_roles]
        print(f"Roles to be added: {missing_roles}")
        
        if not missing_roles:
            print("No missing roles found. Database is up to date.")
            return
            
        if dry_run:
            print("DRY RUN: Would add the following roles:")
            for role in missing_roles:
                print(f"  - {role}")
            return
            
        # Add missing roles
        print("Adding missing roles to database...")
        for role_name in missing_roles:
            role = Role(name=role_name)
            db.add(role)
            
        try:
            db.commit()
            print(f"Successfully added {len(missing_roles)} missing roles to database.")
        except Exception as e:
            db.rollback()
            print(f"Error adding roles: {e}")
            raise

def main():
    parser = argparse.ArgumentParser(description="Add missing roles to database")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without actually doing it"
    )
    args = parser.parse_args()
    
    migrate_missing_roles(dry_run=args.dry_run)

if __name__ == "__main__":
    main()