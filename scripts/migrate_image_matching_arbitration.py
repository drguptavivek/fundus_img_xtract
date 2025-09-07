#!/usr/bin/env python3
"""
Migration script to add matching and arbitration columns to encounter_files and direct_image_uploads tables.

This migration adds the following columns to both tables:
- matched_at: timestamp when the image was matched
- is_locked: boolean indicating if the image is locked for editing
- is_arbitration: boolean indicating if the image has been arbitrated
- arbitrated_by: foreign key to the user who performed arbitration

Usage:
  python scripts/migrate_image_matching_arbitration.py
  python scripts/migrate_image_matching_arbitration.py --dry-run
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, text
from models import DATABASE_URL


def column_exists(conn, table: str, column: str) -> bool:
    """Check if a column exists in a table."""
    if DATABASE_URL.startswith("sqlite"):
        # For SQLite, check the table info
        result = conn.execute(text(f"PRAGMA table_info({table})"))
        columns = [row[1] for row in result]
        return column in columns
    else:
        # For other databases, you might need a different approach
        try:
            result = conn.execute(text(f"""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = '{table}' AND column_name = '{column}'
            """))
            return result.fetchone() is not None
        except Exception:
            # Fallback approach
            try:
                conn.execute(text(f"SELECT {column} FROM {table} LIMIT 1"))
                return True
            except Exception:
                return False


def migrate(dry_run: bool = False) -> None:
    """Add matching and arbitration columns to encounter_files and direct_image_uploads tables."""
    print(f"{'[DRY RUN] ' if dry_run else ''}Adding matching and arbitration columns to encounter_files and direct_image_uploads tables...")
    
    engine = create_engine(DATABASE_URL)
    
    # Columns to add
    columns_to_add = [
        ("matched_at", "DATETIME"),
        ("is_locked", "BOOLEAN DEFAULT FALSE"),
        ("is_arbitration", "BOOLEAN DEFAULT FALSE"),
        ("arbitrated_by", "INTEGER REFERENCES users(id)")
    ]
    
    # Tables to modify
    tables = ["encounter_files", "direct_image_uploads"]
    
    # Check if columns already exist
    all_columns_exist = True
    with engine.connect() as conn:
        for table in tables:
            for column_name, _ in columns_to_add:
                if not column_exists(conn, table, column_name):
                    all_columns_exist = False
                    break
            if not all_columns_exist:
                break
    
    if all_columns_exist:
        print("All columns already exist. Skipping...")
        return
    
    # Prepare statements
    statements = []
    
    if DATABASE_URL.startswith("sqlite"):
        # For SQLite, we need to add columns one by one
        for table in tables:
            for column_name, column_type in columns_to_add:
                if not column_exists(engine.connect(), table, column_name):
                    statements.append(f"ALTER TABLE {table} ADD COLUMN {column_name} {column_type}")
    else:
        # For other databases (PostgreSQL, MySQL, etc.)
        for table in tables:
            columns_sql = []
            with engine.connect() as conn:
                for column_name, column_type in columns_to_add:
                    if not column_exists(conn, table, column_name):
                        columns_sql.append(f"{column_name} {column_type}")
            
            if columns_sql:
                statements.append(f"ALTER TABLE {table} ADD COLUMN {', ADD COLUMN '.join(columns_sql)}")
    
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