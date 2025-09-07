"""
Migration script to add lab_unit_id to PatientEncounters table.
"""

import sys
from pathlib import Path

# Add the project root to the path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from models import engine

def migrate():
    # Add lab_unit_id column to patient_encounters table
    with engine.connect() as conn:
        # Check if column already exists
        result = conn.execute(text("PRAGMA table_info(patient_encounters)"))
        columns = [row[1] for row in result]
        
        if 'lab_unit_id' not in columns:
            print("Adding lab_unit_id column to patient_encounters table...")
            conn.execute(text("ALTER TABLE patient_encounters ADD COLUMN lab_unit_id INTEGER"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_patient_encounters_lab_unit ON patient_encounters (lab_unit_id)"))
            print("Column added successfully.")
        else:
            print("lab_unit_id column already exists.")

if __name__ == "__main__":
    migrate()