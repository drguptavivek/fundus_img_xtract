# scripts/backfill_patient_encounters_lab_unit.py
"""
Script to backfill lab_unit_id = 1 for existing patient encounters.
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


def backfill(dry_run: bool = False) -> None:
    """
    Backfill lab_unit_id = 1 for existing patient encounters where lab_unit_id is NULL.
    
    Args:
        dry_run: If True, only print what would be done without making changes
    """
    print("Preparing to backfill lab_unit_id = 1 for patient encounters...")
    
    # Count how many records need to be updated
    with engine.connect() as conn:
        result = conn.execute(text("SELECT COUNT(*) FROM patient_encounters WHERE lab_unit_id IS NULL"))
        count = result.scalar()
    
    if count == 0:
        print("No patient encounters need to be updated (lab_unit_id is already set for all records).")
        return
    
    print(f"Found {count} patient encounters that need to be updated.")
    
    if dry_run:
        print("DRY RUN - No changes will be made")
        print(f"Would update {count} records in patient_encounters table setting lab_unit_id = 1")
        return
    
    print("Applying changes...")
    
    # Update the records
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            result = conn.execute(
                text("UPDATE patient_encounters SET lab_unit_id = 1 WHERE lab_unit_id IS NULL")
            )
            updated_count = result.rowcount
            trans.commit()
            print(f"Successfully updated {updated_count} patient encounters with lab_unit_id = 1.")
        except Exception as e:
            trans.rollback()
            print(f"Backfill failed: {e}")
            raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill lab_unit_id = 1 for patient encounters")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes"
    )
    args = parser.parse_args()
    
    backfill(dry_run=args.dry_run)