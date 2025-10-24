#!/usr/bin/env python3
"""Add features_json and selected_features_json fields to disease_gradings and grades tables."""
from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import inspect, text

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from models import engine  # noqa: E402

# Disease gradings table
DISEASE_GRADINGS_TABLE = "disease_gradings"
DISEASE_GRADINGS_COLUMN = "features_json"
DISEASE_GRADINGS_COLUMN_TYPE = "TEXT"

# Grades table
GRADES_TABLE = "grades"
GRADES_COLUMN = "selected_features_json"
GRADES_COLUMN_TYPE = "TEXT"


def column_exists(table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table."""
    inspector = inspect(engine)
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def add_column(table_name: str, column_name: str, column_type: str) -> None:
    """Add a column to a table."""
    ddl = f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
    with engine.begin() as conn:
        conn.execute(text(ddl))


def main() -> None:
    """Main migration function."""
    print("Starting migration: Add features_json and selected_features_json fields...")
    
    # Check and add features_json to disease_gradings table
    if column_exists(DISEASE_GRADINGS_TABLE, DISEASE_GRADINGS_COLUMN):
        print(f"Column '{DISEASE_GRADINGS_COLUMN}' already exists on '{DISEASE_GRADINGS_TABLE}'. Nothing to do.")
    else:
        try:
            add_column(DISEASE_GRADINGS_TABLE, DISEASE_GRADINGS_COLUMN, DISEASE_GRADINGS_COLUMN_TYPE)
            print(f"Column '{DISEASE_GRADINGS_COLUMN}' added to '{DISEASE_GRADINGS_TABLE}' successfully.")
        except Exception as e:
            print(f"Failed to add column '{DISEASE_GRADINGS_COLUMN}' to '{DISEASE_GRADINGS_TABLE}': {e}")
            raise
    
    # Check and add selected_features_json to grades table
    if column_exists(GRADES_TABLE, GRADES_COLUMN):
        print(f"Column '{GRADES_COLUMN}' already exists on '{GRADES_TABLE}'. Nothing to do.")
    else:
        try:
            add_column(GRADES_TABLE, GRADES_COLUMN, GRADES_COLUMN_TYPE)
            print(f"Column '{GRADES_COLUMN}' added to '{GRADES_TABLE}' successfully.")
        except Exception as e:
            print(f"Failed to add column '{GRADES_COLUMN}' to '{GRADES_TABLE}': {e}")
            raise
    
    print("Migration completed successfully!")


if __name__ == "__main__":
    main()
