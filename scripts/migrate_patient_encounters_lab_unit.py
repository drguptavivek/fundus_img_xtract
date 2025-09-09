# scripts/migrate_patient_encounters_lab_unit.py
"""
Migration script to add lab_unit_id column to patient_encounters table.
"""

import argparse
import sys
from pathlib import Path

# Add the project root to the path so we can import models
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import text
from models import engine


def migrate(dry_run: bool = False) -> None:
    """
    Add lab_unit_id column to patient_encounters table.
    
    Args:
        dry_run: If True, only print what would be done without making changes
    """
    print("Preparing to add lab_unit_id column to patient_encounters table...")
    
    # Check if column already exists
    with engine.connect() as conn:
        result = conn.execute(text("PRAGMA table_info(patient_encounters)"))
        columns = [row[1] for row in result]
        
    if "lab_unit_id" in columns:
        print("Column 'lab_unit_id' already exists in patient_encounters table.")
        return
    
    if dry_run:
        print("DRY RUN - No changes will be made")
        print("Would execute: ALTER TABLE patient_encounters ADD COLUMN lab_unit_id INTEGER")
        print("Would execute: CREATE INDEX IF NOT EXISTS ix_patient_encounters_lab_unit_id ON patient_encounters (lab_unit_id)")
        return
    
    print("Applying changes...")
    
    # Add the column
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            conn.execute(text("ALTER TABLE patient_encounters ADD COLUMN lab_unit_id INTEGER"))
            print("Successfully added 'lab_unit_id' column to patient_encounters table.")
            
            # Create index on the new column
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_patient_encounters_lab_unit_id ON patient_encounters (lab_unit_id)"))
            print("Successfully created index on patient_encounters.lab_unit_id.")
            
            trans.commit()
            print("Migration completed successfully.")
        except Exception as e:
            trans.rollback()
            print(f"Migration failed: {e}")
            raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Add lab_unit_id column to patient_encounters table")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes"
    )
    args = parser.parse_args()
    
    migrate(dry_run=args.dry_run)