# scripts/migrate_direct_uploads_matching_fields.py
"""
Migration script to add matching fields to direct_image_uploads table.
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
    Add matching fields to direct_image_uploads table.
    
    Args:
        dry_run: If True, only print what would be done without making changes
    """
    print("Preparing to add matching fields to direct_image_uploads table...")
    
    # Check existing columns
    with engine.connect() as conn:
        result = conn.execute(text("PRAGMA table_info(direct_image_uploads)"))
        columns = [row[1] for row in result]
    
    # Columns to add
    columns_to_add = [
        ("matched_at", "DATETIME"),
        ("is_locked", "BOOLEAN DEFAULT 0"),
        ("is_arbitration", "BOOLEAN DEFAULT 0"),
        ("arbitrated_by", "INTEGER")
    ]
    
    # Check which columns need to be added
    columns_needed = [(name, type_def) for name, type_def in columns_to_add if name not in columns]
    
    if not columns_needed:
        print("All matching fields already exist in direct_image_uploads table.")
        return
    
    print(f"Need to add {len(columns_needed)} columns: {[name for name, _ in columns_needed]}")
    
    if dry_run:
        print("DRY RUN - No changes will be made")
        for name, type_def in columns_needed:
            print(f"Would execute: ALTER TABLE direct_image_uploads ADD COLUMN {name} {type_def}")
        print("Would create indexes for the new columns")
        return
    
    print("Applying changes...")
    
    # Add the columns
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            for name, type_def in columns_needed:
                conn.execute(text(f"ALTER TABLE direct_image_uploads ADD COLUMN {name} {type_def}"))
                print(f"Successfully added '{name}' column to direct_image_uploads table.")
            
            # Create indexes
            index_queries = [
                "CREATE INDEX IF NOT EXISTS ix_direct_image_uploads_matched_at ON direct_image_uploads (matched_at)",
                "CREATE INDEX IF NOT EXISTS ix_direct_image_uploads_is_locked ON direct_image_uploads (is_locked)",
                "CREATE INDEX IF NOT EXISTS ix_direct_image_uploads_is_arbitration ON direct_image_uploads (is_arbitration)",
                "CREATE INDEX IF NOT EXISTS ix_direct_image_uploads_arbitrated_by ON direct_image_uploads (arbitrated_by)"
            ]
            
            for query in index_queries:
                conn.execute(text(query))
                print(f"Created index for direct_image_uploads table.")
            
            trans.commit()
            print("Migration completed successfully.")
        except Exception as e:
            trans.rollback()
            print(f"Migration failed: {e}")
            raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Add matching fields to direct_image_uploads table")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes"
    )
    args = parser.parse_args()
    
    migrate(dry_run=args.dry_run)