#!/usr/bin/env python3
"""
Script to verify that the database tables are empty and essential directories exist and are empty
"""

import sys
import os
# Add the project root directory to the path so we can import models
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import GradingTask, Grade, Consensus, EncounterFile, Job, JobItem
from db_transaction_manager import get_db_session


def verify_empty():
    """Verify that the database tables are empty and essential directories exist and are empty."""
    with get_db_session() as db:
        # Check database tables
        task_count = db.query(GradingTask).count()
        grade_count = db.query(Grade).count()
        consensus_count = db.query(Consensus).count()
        encounter_count = db.query(EncounterFile).count()
        job_count = db.query(Job).count()
        jobitem_count = db.query(JobItem).count()
        
        print(f'Grading Tasks: {task_count}')
        print(f'Grades: {grade_count}')
        print(f'Consensus: {consensus_count}')
        print(f'Encounter Files: {encounter_count}')
        print(f'Jobs: {job_count}')
        print(f'Job Items: {jobitem_count}')
        
        # Check essential directories
        files_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "files")
        essential_dirs = [
            "zip_upload_zips",
            "zips_upload_processed", 
            "zip_upload_processing_error",
            "zip_upload_images",
            "direct_uploads",
            "zip_upload_pdfs",
            "zip_dr_pdfs",
            "zip_glaucoma_pdfs",
            "upload_meta"
        ]
        
        print("\nChecking essential directories:")
        all_dirs_empty = True
        for dir_name in essential_dirs:
            dir_path = os.path.join(files_dir, dir_name)
            if os.path.exists(dir_path) and os.path.isdir(dir_path):
                dir_contents = os.listdir(dir_path)
                print(f'{dir_name}: {"Empty" if len(dir_contents) == 0 else f"Has {len(dir_contents)} items"}')
                if len(dir_contents) > 0:
                    all_dirs_empty = False
                    print(f'  Contents: {dir_contents[:5]}{"..." if len(dir_contents) > 5 else ""}')  # Show first 5 items if more
            else:
                print(f'{dir_name}: MISSING or NOT A DIRECTORY')
                all_dirs_empty = False
        
        # Overall status
        db_empty = task_count == 0 and grade_count == 0 and consensus_count == 0 and encounter_count == 0 and job_count == 0 and jobitem_count == 0
        
        if db_empty and all_dirs_empty:
            print("\nAll tables and essential directories are empty - verification successful!")
        else:
            print(f"\nDatabase empty: {db_empty}")
            print(f"Directories empty: {all_dirs_empty}")
            print("Verification failed!")


if __name__ == "__main__":
    verify_empty()