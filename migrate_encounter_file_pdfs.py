"""
Migration script to separate EncounterFilePDFs into a unique table.
Retains EncounterFiles for images only.

Usage:
  python scripts/setup_db.py --migrate-encounter-file-pdfs
  python scripts/setup_db.py --migrate-encounter-file-pdfs --check-only
"""

from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import sys
from pathlib import Path

# Ensure project root is importable when running this script directly
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Ensure env is loaded (DATABASE_URL, etc.)
load_dotenv()

from models import Base, engine  # noqa: E402


def migrate_encounter_file_pdfs(check_only: bool = False) -> None:
    """
    Migrate PDF files from encounter_files table to a new encounter_file_pdfs table.
    """
    print("Preparing to migrate PDF files from encounter_files to encounter_file_pdfs table...")
    
    with sessionmaker(bind=engine)() as db:
        try:
            # Check if the new table already exists
            result = db.execute(text("""
                SELECT name FROM sqlite_master WHERE type='table' AND name='encounter_file_pdfs'
            """)).fetchone()
            
            if result is None and not check_only:
                # Create the new table
                print("Creating encounter_file_pdfs table...")
                db.execute(text("""
                    CREATE TABLE encounter_file_pdfs (
                        id INTEGER PRIMARY KEY,
                        patient_encounter_id INTEGER NOT NULL,
                        filename TEXT NOT NULL,
                        file_type TEXT NOT NULL,
                        ocr_processed BOOLEAN DEFAULT 0 NOT NULL,
                        uuid TEXT UNIQUE,
                        eye_side TEXT,
                        lab_unit_id INTEGER,
                        matched_at DATETIME,
                        is_locked BOOLEAN DEFAULT 0 NOT NULL,
                        is_arbitration BOOLEAN DEFAULT 0 NOT NULL,
                        arbitrated_by INTEGER,
                        FOREIGN KEY (patient_encounter_id) REFERENCES patient_encounters (id),
                        FOREIGN KEY (lab_unit_id) REFERENCES lab_units (id),
                        FOREIGN KEY (arbitrated_by) REFERENCES users (id)
                    )
                """))
                
                # Create indexes
                db.execute(text("""
                    CREATE INDEX IF NOT EXISTS ix_encounter_file_pdfs_patient_encounter_id 
                    ON encounter_file_pdfs (patient_encounter_id)
                """))
                db.execute(text("""
                    CREATE INDEX IF NOT EXISTS ix_encounter_file_pdfs_uuid 
                    ON encounter_file_pdfs (uuid)
                """))
                db.execute(text("""
                    CREATE INDEX IF NOT EXISTS ix_encounter_file_pdfs_eye_side 
                    ON encounter_file_pdfs (eye_side)
                """))
                db.execute(text("""
                    CREATE INDEX IF NOT EXISTS ix_encounter_file_pdfs_lab_unit_id 
                    ON encounter_file_pdfs (lab_unit_id)
                """))
                db.execute(text("""
                    CREATE INDEX IF NOT EXISTS ix_encounter_file_pdfs_matched_at 
                    ON encounter_file_pdfs (matched_at)
                """))
                db.execute(text("""
                    CREATE INDEX IF NOT EXISTS ix_encounter_file_pdfs_is_locked 
                    ON encounter_file_pdfs (is_locked)
                """))
                db.execute(text("""
                    CREATE INDEX IF NOT EXISTS ix_encounter_file_pdfs_is_arbitration 
                    ON encounter_file_pdfs (is_arbitration)
                """))
                db.execute(text("""
                    CREATE INDEX IF NOT EXISTS ix_encounter_file_pdfs_arbitrated_by 
                    ON encounter_file_pdfs (arbitrated_by)
                """))
                
                print("encounter_file_pdfs table created successfully.")
            
            # Count PDF files in encounter_files table
            pdf_count = db.execute(text("""
                SELECT COUNT(*) FROM encounter_files WHERE file_type = 'pdf'
            """)).fetchone()[0]
            
            print(f"Found {pdf_count} PDF files in encounter_files table.")
            
            if check_only:
                print("Check-only mode: No changes will be made.")
                return
            
            if pdf_count > 0:
                # Move PDF files to the new table
                print("Moving PDF files to encounter_file_pdfs table...")
                db.execute(text("""
                    INSERT INTO encounter_file_pdfs (
                        id, patient_encounter_id, filename, file_type, ocr_processed, uuid,
                        eye_side, lab_unit_id, matched_at, is_locked, is_arbitration, arbitrated_by
                    )
                    SELECT 
                        id, patient_encounter_id, filename, file_type, ocr_processed, uuid,
                        eye_side, lab_unit_id, matched_at, is_locked, is_arbitration, arbitrated_by
                    FROM encounter_files 
                    WHERE file_type = 'pdf'
                """))
                
                # Delete PDF files from encounter_files table
                db.execute(text("""
                    DELETE FROM encounter_files WHERE file_type = 'pdf'
                """))
                
                print(f"Moved {pdf_count} PDF files to encounter_file_pdfs table.")
            
            # Commit changes
            db.commit()
            print("Migration completed successfully.")
            
        except Exception as e:
            db.rollback()
            print(f"Migration failed: {e}")
            raise


if __name__ == "__main__":
    # Check if --check-only flag is provided
    check_only = "--check-only" in sys.argv
    migrate_encounter_file_pdfs(check_only=check_only)