"""
Database migration script to remove matching and arbitration fields from EncounterFilePDF and DirectImageUpload tables.

This script removes the following columns that were used for dual grading, matching, and arbitration functionality:
- matched_at
- is_locked
- is_arbitration
- arbitrated_by

These fields are no longer needed after removing the dual grading, matching, and arbitration workflows.

Usage:
  python scripts/migrate_remove_matching_arbitration_fields.py
  python scripts/migrate_remove_matching_arbitration_fields.py --dry-run
"""

import os
import sys
from pathlib import Path

# Ensure project root is importable when running this script directly
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

# Load environment variables
load_dotenv()

from models import engine


def migrate(dry_run: bool = False) -> None:
    """Remove matching and arbitration fields from database tables."""
    print(f"Preparing to remove matching and arbitration fields from database tables...")
    print(f"Dry run: {dry_run}")
    
    # Create a session
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    
    try:
        # List of columns to remove
        columns_to_remove = [
            'matched_at',
            'is_locked', 
            'is_arbitration',
            'arbitrated_by'
        ]
        
        # List of tables to modify
        tables_to_modify = [
            'encounter_file_pdfs',
            'direct_image_uploads'
        ]
        
        # Check if we're working with SQLite (different syntax for dropping columns)
        is_sqlite = engine.url.get_backend_name() == 'sqlite'
        
        for table in tables_to_modify:
            print(f"\nProcessing table: {table}")
            
            for column in columns_to_remove:
                try:
                    # Check if column exists
                    if is_sqlite:
                        # For SQLite, we need to check the table info
                        result = db.execute(text(f"PRAGMA table_info({table})"))
                        columns = [row[1] for row in result.fetchall()]
                        column_exists = column in columns
                    else:
                        # For other databases, we can query the information schema
                        result = db.execute(text("""
                            SELECT column_name 
                            FROM information_schema.columns 
                            WHERE table_name = :table_name AND column_name = :column_name
                        """), {"table_name": table, "column_name": column})
                        column_exists = result.fetchone() is not None
                    
                    if column_exists:
                        print(f"  Removing column: {column}")
                        if not dry_run:
                            if is_sqlite:
                                # For SQLite, we need to do the following:
                                # 1. Create new table without the columns
                                # 2. Copy data from old table to new table
                                # 3. Drop old table
                                # 4. Rename new table to old table name
                                
                                # Get the current table schema
                                result = db.execute(text(f"PRAGMA table_info({table})"))
                                table_info = result.fetchall()
                                
                                # Build new table schema without the columns to remove
                                new_columns = []
                                for row in table_info:
                                    col_name = row[1]
                                    col_type = row[2]
                                    notnull = row[3]
                                    default_value = row[4]
                                    pk = row[5]
                                    
                                    # Skip columns we want to remove
                                    if col_name in columns_to_remove:
                                        continue
                                    
                                    # Build column definition
                                    col_def = f"{col_name} {col_type}"
                                    if pk == 1:
                                        col_def += " PRIMARY KEY"
                                    if notnull == 1 and pk != 1:
                                        col_def += " NOT NULL"
                                    if default_value is not None and pk != 1:
                                        if isinstance(default_value, str):
                                            col_def += f" DEFAULT '{default_value}'"
                                        else:
                                            col_def += f" DEFAULT {default_value}"
                                            
                                    new_columns.append(col_def)
                                
                                new_table_name = f"{table}_new"
                                
                                # Create new table
                                create_sql = f"CREATE TABLE {new_table_name} ({', '.join(new_columns)})"
                                print(f"    Creating new table: {create_sql}")
                                db.execute(text(create_sql))
                                
                                # Copy data (only columns that exist in new table)
                                new_col_names = [col.split()[0] for col in new_columns]
                                insert_sql = f"INSERT INTO {new_table_name} ({', '.join(new_col_names)}) SELECT {', '.join(new_col_names)} FROM {table}"
                                print(f"    Copying data: {insert_sql}")
                                db.execute(text(insert_sql))
                                
                                # Drop old table
                                print(f"    Dropping old table: {table}")
                                db.execute(text(f"DROP TABLE {table}"))
                                
                                # Rename new table
                                print(f"    Renaming new table to: {table}")
                                db.execute(text(f"ALTER TABLE {new_table_name} RENAME TO {table}"))
                                
                            else:
                                # For other databases like PostgreSQL, MySQL
                                db.execute(text(f"ALTER TABLE {table} DROP COLUMN {column}"))
                    else:
                        print(f"  Column {column} does not exist in {table} - skipping")
                        
                except Exception as e:
                    print(f"  Error processing column {column} in table {table}: {e}")
                    if not dry_run:
                        raise
        
        if not dry_run:
            db.commit()
            print("\nMigration completed successfully!")
        else:
            print("\nDry run completed. No changes were made to the database.")
            
    except Exception as e:
        if not dry_run:
            db.rollback()
        print(f"Error during migration: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Remove matching and arbitration fields from database tables")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without actually making changes"
    )
    
    args = parser.parse_args()
    migrate(dry_run=args.dry_run)