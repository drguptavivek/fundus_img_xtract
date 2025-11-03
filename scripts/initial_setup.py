#!/usr/bin/env python3
"""Initial setup script for the Fundus Image Manager.

This script deletes existing database, sets up core entities (hospitals, lab units, cameras, areas),
creates core diseases and their gradings, adds test users, and populates sample features
for disease gradings.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
import shutil
from datetime import datetime

# Add the project root to the Python path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import select
from models import Base, engine, Session, Hospital, LabUnit, Camera, Area, Disease, DiseaseGrading, GradingsFeatures, User
from models import UPLOAD_DIR, PROCESSED_DIR, PROCESSING_ERROR_DIR, IMAGE_DIR
from models import DIRECT_UPLOAD_DIR, PDF_DIR, DR_PDF_DIR, GLAUCOMA_PDF_DIR
from models import SUCCESS_LOG, ERROR_LOG
from dotenv import load_dotenv

# Import all core entity definitions and setup functions
from scripts.setup_core_entities import (
    CORE_HOSPITALS, CORE_LAB_UNITS, CORE_CAMERAS, CORE_AREAS, CORE_DISEASES,
    STANDARD_GRADINGS, SAMPLE_FEATURES,
    setup_all_core_entities, populate_sample_features
)
from scripts.remove_test_users import remove_test_users

def reset_files_directory() -> None:
    """Clear the files directory and recreate required sub-directories."""
    files_root = project_root / "files"
    resolved_root = files_root.resolve()
    if project_root not in resolved_root.parents and resolved_root != project_root:
        raise RuntimeError(f"Refusing to delete non-project directory: {resolved_root}")

    if resolved_root.exists():
        print(f"Clearing files directory at {resolved_root}...")
        shutil.rmtree(resolved_root)
    resolved_root.mkdir(parents=True, exist_ok=True)
    print(f"  Recreated files directory: {resolved_root}")

    create_directories()


def backup_database() -> bool:
    """Create a timestamped backup of the current database using backup_db.py functionality.
    
    Returns:
        bool: True if backup was successful, False otherwise
    """
    # Import backup functions from backup_db.py
    from scripts.backup_db import get_database_info, create_sqlite_backup, create_postgresql_backup
    
    # Load environment variables
    load_dotenv()
    
    # Get database information
    db_info = get_database_info()
    if not db_info:
        print("No database path configured; skipping database backup.")
        return False
    
    print(f"Database type: {db_info['type']}")
    
    # Ensure backups directory exists
    backups_dir = project_root / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)
    print(f"Backup directory: {backups_dir}")
    
    # Create backup based on database type
    if db_info["type"] == "sqlite":
        if not os.path.exists(db_info["path"]):
            print(f"No database file found at {db_info['path']}; skipping backup.")
            return False
        
        backup_file = create_sqlite_backup(db_info["path"], backups_dir)
        
    elif db_info["type"] == "postgresql":
        backup_file = create_postgresql_backup(db_info, backups_dir)
        
    else:
        print(f"Unsupported database type: {db_info['type']}")
        return False
    
    if backup_file:
        # Get file size for reporting
        file_size = backup_file.stat().st_size
        file_size_mb = file_size / (1024 * 1024)
        
        print(f"SUCCESS: Backup created!")
        print(f"File: {backup_file.name}")
        print(f"Size: {file_size_mb:.2f} MB")
        print(f"Location: {backup_file}")
        return True
    else:
        print("ERROR: Backup failed!")
        return False

def remove_database() -> None:
    """Remove the existing database after backup."""
    from models import DATABASE_URL
    
    if DATABASE_URL.startswith("sqlite"):
        # For SQLite, remove the database file
        db_path_str = engine.url.database
        if not db_path_str:
            print("No database path configured; skipping database removal.")
            return

        db_path = Path(db_path_str)
        if not db_path.is_absolute():
            db_path = project_root / db_path

        if db_path.exists():
            print("Removing original database file...")
            engine.dispose()
            db_path.unlink()
            print("  Database file removed.")
        else:
            print(f"No database file found at {db_path}; skipping removal.")
    elif DATABASE_URL.startswith("postgresql"):
        # For PostgreSQL, drop all tables
        print("Dropping all tables in PostgreSQL database...")
        Base.metadata.drop_all(engine)
        print("  All tables dropped.")
    else:
        print(f"Unsupported database type for removal: {DATABASE_URL}")

def backup_and_remove_database() -> None:
    """Create a timestamped backup of the current database, then delete it."""
    # First create backup
    backup_success = backup_database()
    
    if backup_success:
        # Then remove the database
        remove_database()
    else:
        print("Skipping database removal due to backup failure.")


def create_directories() -> None:
    """Create all required directories if they are missing."""
    print("Preparing required directories...")

    directories = [
        UPLOAD_DIR,
        PROCESSED_DIR,
        PROCESSING_ERROR_DIR,
        IMAGE_DIR,
        DIRECT_UPLOAD_DIR,
        PDF_DIR,
        DR_PDF_DIR,
        GLAUCOMA_PDF_DIR,
        SUCCESS_LOG.parent,
        ERROR_LOG.parent,
    ]

    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
        print(f"  Ready: {directory}")

def create_database():
    """Create a new blank database with all tables."""
    print("Creating database tables...")
    
    # For PostgreSQL, tables were already dropped in remove_database()
    # For SQLite, the file was already removed, so no need to drop tables
    # But we'll check and drop if they exist to be safe
    from models import DATABASE_URL
    
    if DATABASE_URL.startswith("postgresql"):
        # Tables were already dropped in remove_database()
        pass
    else:
        # For SQLite or other databases, drop tables if they exist
        Base.metadata.drop_all(engine)
    
    # Create all tables
    Base.metadata.create_all(engine)
    print("  Database tables created successfully!")

def confirm_database_reset():
    """Ask for user confirmation before resetting the database."""
    print("⚠️  WARNING: This will completely reset the database!")
    print("   - All existing data will be permanently deleted")
    print("   - A backup will be created before deletion")
    print()
    
    response = input("Do you want to continue? (yes/no): ").strip().lower()
    if response not in ['yes', 'y']:
        print("Database reset cancelled by user.")
        return False
    
    print("Proceeding with database reset...")
    return True

def main():
    """Main function to run the initial setup."""
    import argparse
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Initial setup for Fundus Image Manager')
    parser.add_argument('--force', action='store_true',
                       help='Skip confirmation prompt and proceed with database reset')
    args = parser.parse_args()
    
    print("🚀 Starting initial setup for Fundus Image Manager...")
    print("=" * 50)
    
    try:
        # Confirm database reset (unless --force is specified)
        if not args.force and not confirm_database_reset():
            print("Setup cancelled.")
            return
        
        if args.force:
            print("Proceeding with database reset (force mode)...")
        
        # Reset storage directories
        reset_files_directory()
        print()

        # Backup and remove existing database
        backup_and_remove_database()
        print()
        
        # Create database
        create_database()
        print()
        
        # Setup core data
        with Session() as db:
            setup_all_core_entities(db)
            db.commit()
        print()

        print("Removing any existing test users...")
        remove_test_users()
        print()
        
        print("Populating sample features for disease gradings...")
        populate_sample_features()
        
        print()
        print("✅ Initial setup completed successfully!")
        print()
        print("Summary:")
        with Session() as db:
            hospitals = db.execute(select(Hospital)).scalars().all()
            lab_units = db.execute(select(LabUnit)).scalars().all()
            cameras = db.execute(select(Camera)).scalars().all()
            areas = db.execute(select(Area)).scalars().all()
            diseases = db.execute(select(Disease)).scalars().all()
            gradings = db.execute(select(DiseaseGrading)).scalars().all()
            users = db.execute(select(User)).scalars().all()
            
            print(f"  Hospitals: {len(hospitals)}")
            print(f"  Lab Units: {len(lab_units)}")
            print(f"  Cameras: {len(cameras)}")
            print(f"  Areas: {len(areas)}")
            print(f"  Diseases: {len(diseases)}")
            print(f"  Disease Gradings: {len(gradings)}")
            features = db.execute(select(GradingsFeatures)).scalars().all()
            print(f"  Grading Features: {len(features)}")
            print(f"  Users: {len(users)}")
        
        print()

        print()
        print("Next steps:")
        print("1. Create users: python scripts/create_user.py <username>")
        print("2. Assign roles: python scripts/assign_roles.py <username> --roles <role1> <role2>")
        print("3. Start the application: python app.py")
        print("4. Review the populated sample features in the admin interface")
        
    except Exception as e:
        print(f"\n❌ Error during initial setup: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
