"""
Migration script to add lab_unit_id to EncounterFile table.
"""

import sys
from pathlib import Path

# Add the project root to the path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from models import engine

def migrate():
    # Add lab_unit_id column to encounter_files table
    with engine.connect() as conn:
        # Check if column already exists
        result = conn.execute(text("PRAGMA table_info(encounter_files)"))
        columns = [row[1] for row in result]
        
        if 'lab_unit_id' not in columns:
            print("Adding lab_unit_id column to encounter_files table...")
            conn.execute(text("ALTER TABLE encounter_files ADD COLUMN lab_unit_id INTEGER"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_encounter_files_lab_unit ON encounter_files (lab_unit_id)"))
            print("Column added successfully.")
        else:
            print("lab_unit_id column already exists.")

if __name__ == "__main__":
    migrate()