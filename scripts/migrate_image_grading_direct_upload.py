#!/usr/bin/env python3
"""
Migration script to add direct_image_upload_id column to image_gradings table.

This migration:
1. Adds direct_image_upload_id column to image_gradings table
2. Adds indexes for the new column
3. Adds check constraint to ensure either encounter_file_id or direct_image_upload_id is set but not both
4. Adds foreign key constraint to direct_image_uploads table

Usage:
  python scripts/migrate_image_grading_direct_upload.py
  python scripts/migrate_image_grading_direct_upload.py --dry-run
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, text
from models import DATABASE_URL


def migrate(dry_run: bool = False) -> None:
    print(f"{'[DRY RUN] ' if dry_run else ''}Adding direct_image_upload_id column to image_gradings table...")
    
    engine = create_engine(DATABASE_URL)
    
    # Check if column already exists
    column_exists = False
    if DATABASE_URL.startswith("sqlite"):
        # For SQLite, check the table info
        with engine.connect() as conn:
            result = conn.execute(text("PRAGMA table_info(image_gradings)"))
            columns = [row[1] for row in result]
            column_exists = "direct_image_upload_id" in columns
    else:
        # For other databases, you might need a different approach
        # This is a simplified check - in production, you'd want a more robust solution
        try:
            with engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'image_gradings' AND column_name = 'direct_image_upload_id'
                """))
                column_exists = result.fetchone() is not None
        except Exception:
            # Fallback approach
            try:
                with engine.connect() as conn:
                    conn.execute(text("SELECT direct_image_upload_id FROM image_gradings LIMIT 1"))
                column_exists = True
            except Exception:
                column_exists = False
    
    if column_exists:
        print("Column direct_image_upload_id already exists. Skipping...")
        return
    
    # Add the column and constraints
    statements = []
    
    if DATABASE_URL.startswith("sqlite"):
        # SQLite approach - requires recreating the table
        statements = [
            # Add the column
            "ALTER TABLE image_gradings ADD COLUMN direct_image_upload_id INTEGER REFERENCES direct_image_uploads(id)",
            # Add indexes
            "CREATE INDEX IF NOT EXISTS ix_image_gradings_direct_image_upload_id ON image_gradings(direct_image_upload_id)",
            # Add check constraint (SQLite will ignore this but it's here for documentation)
            "CREATE INDEX IF NOT EXISTS ix_image_gradings_direct_user_role_for ON image_gradings(direct_image_upload_id, grader_user_id, grader_role, graded_for)",
        ]
    else:
        # For other databases (PostgreSQL, MySQL, etc.)
        statements = [
            # Add the column
            "ALTER TABLE image_gradings ADD COLUMN direct_image_upload_id INTEGER REFERENCES direct_image_uploads(id)",
            # Add indexes
            "CREATE INDEX IF NOT EXISTS ix_image_gradings_direct_image_upload_id ON image_gradings(direct_image_upload_id)",
            "CREATE INDEX IF NOT EXISTS ix_image_gradings_direct_user_role_for ON image_gradings(direct_image_upload_id, grader_user_id, grader_role, graded_for)",
            # Add check constraint
            """
            ALTER TABLE image_gradings ADD CONSTRAINT ck_image_grading_either_encounter_or_direct
            CHECK (
                (encounter_file_id IS NOT NULL AND direct_image_upload_id IS NULL) OR 
                (encounter_file_id IS NULL AND direct_image_upload_id IS NOT NULL)
            )
            """
        ]
    
    if dry_run:
        print("Would execute the following statements:")
        for stmt in statements:
            print(f"  {stmt}")
        print("DRY RUN: No changes made.")
        return
    
    # Execute the statements
    try:
        with engine.connect() as conn:
            for stmt in statements:
                if stmt.strip():  # Skip empty statements
                    print(f"Executing: {stmt}")
                    conn.execute(text(stmt))
            conn.commit()
        print("Migration completed successfully.")
    except Exception as e:
        print(f"Migration failed: {e}")
        if not dry_run:
            raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without making changes")
    args = parser.parse_args()
    
    migrate(dry_run=args.dry_run)