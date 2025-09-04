#!/usr/bin/env python3
"""
Migration script to modify image_gradings table to allow NULL values for encounter_file_id and direct_image_upload_id.

This migration:
1. Modifies the encounter_file_id column to allow NULL values
2. Modifies the direct_image_upload_id column to allow NULL values
3. Ensures the check constraint is properly defined
4. Fixes existing records that violate the constraint

Usage:
  python scripts/migrate_image_grading_nullable_columns.py
  python scripts/migrate_image_grading_nullable_columns.py --dry-run
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
    print(f"{'[DRY RUN] ' if dry_run else ''}Modifying image_gradings table to allow NULL values for encounter_file_id and direct_image_upload_id...")
    
    engine = create_engine(DATABASE_URL)
    
    # For SQLite, we need to recreate the table
    if DATABASE_URL.startswith("sqlite"):
        statements = [
            # Create new table with correct schema (without constraint first)
            """
            CREATE TABLE image_gradings_new (
                id INTEGER NOT NULL PRIMARY KEY,
                encounter_file_id INTEGER REFERENCES encounter_files(id),
                direct_image_upload_id INTEGER REFERENCES direct_image_uploads(id),
                grader_user_id INTEGER REFERENCES users(id),
                grader_username VARCHAR(150),
                grader_role VARCHAR(32),
                graded_for VARCHAR(32),
                impression VARCHAR(32),
                remarks TEXT,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            )
            """,
            # Copy data from old table
            """
            INSERT INTO image_gradings_new (
                id, encounter_file_id, direct_image_upload_id, grader_user_id, grader_username, 
                grader_role, graded_for, impression, remarks, created_at, updated_at
            )
            SELECT 
                id, encounter_file_id, direct_image_upload_id, grader_user_id, grader_username, 
                grader_role, graded_for, impression, remarks, created_at, updated_at
            FROM image_gradings
            """,
            # Fix existing records that violate the constraint
            """
            UPDATE image_gradings_new 
            SET encounter_file_id = NULL 
            WHERE encounter_file_id = 'NA' AND direct_image_upload_id IS NOT NULL
            """,
            # Add the check constraint
            """
            CREATE TABLE image_gradings_final (
                id INTEGER NOT NULL PRIMARY KEY,
                encounter_file_id INTEGER REFERENCES encounter_files(id),
                direct_image_upload_id INTEGER REFERENCES direct_image_uploads(id),
                grader_user_id INTEGER REFERENCES users(id),
                grader_username VARCHAR(150),
                grader_role VARCHAR(32),
                graded_for VARCHAR(32),
                impression VARCHAR(32),
                remarks TEXT,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                CONSTRAINT ck_image_grading_either_encounter_or_direct CHECK (
                    (encounter_file_id IS NOT NULL AND direct_image_upload_id IS NULL) OR 
                    (encounter_file_id IS NULL AND direct_image_upload_id IS NOT NULL)
                )
            )
            """,
            # Copy data again
            """
            INSERT INTO image_gradings_final (
                id, encounter_file_id, direct_image_upload_id, grader_user_id, grader_username, 
                grader_role, graded_for, impression, remarks, created_at, updated_at
            )
            SELECT 
                id, encounter_file_id, direct_image_upload_id, grader_user_id, grader_username, 
                grader_role, graded_for, impression, remarks, created_at, updated_at
            FROM image_gradings_new
            """,
            # Drop old tables and rename new one
            "DROP TABLE image_gradings",
            "DROP TABLE image_gradings_new",
            "ALTER TABLE image_gradings_final RENAME TO image_gradings"
        ]
    else:
        # For other databases (PostgreSQL, MySQL, etc.)
        statements = [
            # Fix existing records that violate the constraint by creating a temporary table
            """
            CREATE TEMPORARY TABLE temp_fix AS
            SELECT 
                id, 
                CASE WHEN encounter_file_id = 'NA' THEN NULL ELSE encounter_file_id END as encounter_file_id,
                direct_image_upload_id, 
                grader_user_id, 
                grader_username, 
                grader_role, 
                graded_for, 
                impression, 
                remarks, 
                created_at, 
                updated_at
            FROM image_gradings
            """,
            # Modify columns to allow NULL
            "ALTER TABLE image_gradings ALTER COLUMN encounter_file_id DROP NOT NULL",
            "ALTER TABLE image_gradings ALTER COLUMN direct_image_upload_id DROP NOT NULL",
            # Update the data
            """
            UPDATE image_gradings 
            SET encounter_file_id = NULL 
            WHERE encounter_file_id = 'NA' AND direct_image_upload_id IS NOT NULL
            """,
            # Ensure check constraint exists
            """
            ALTER TABLE image_gradings DROP CONSTRAINT IF EXISTS ck_image_grading_either_encounter_or_direct,
            ADD CONSTRAINT ck_image_grading_either_encounter_or_direct CHECK (
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