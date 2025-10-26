#!/usr/bin/env python3
"""
Script to identify tasks with missing image files on disk.
Checks both GradingTask and IntraRaterTask tables for missing image files.
"""

import os
import sys
from pathlib import Path
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine

# Add the parent directory to the path to import models
sys.path.append(str(Path(__file__).parent.parent))

from models import (
    Base, 
    GradingTask, 
    IntraRaterTask,
    EncounterFile,
    DirectImageUpload,
    Session as DBSession,
    IMAGE_DIR,
    DIRECT_UPLOAD_DIR,
    DATABASE_URL
)

def check_encounter_file_exists(encounter_file, db_session):
    """Check if an encounter file exists on disk."""
    if not encounter_file or not encounter_file.filename:
        return False, "No filename in database record"
    
    # Get the upload date from the related patient encounter
    from models import PatientEncounters, ZipFile
    result = (
        db_session.query(PatientEncounters, ZipFile)
        .join(ZipFile, PatientEncounters.zip_file_id == ZipFile.id)
        .filter(PatientEncounters.id == encounter_file.patient_encounter_id)
        .first()
    )
    
    if not result:
        return False, "No patient encounter found"
    
    patient_encounter, zip_file = result
    if not zip_file.upload_date:
        return False, "No upload date"
    
    upload_date_str = zip_file.upload_date.strftime("%Y_%m_%d") if zip_file.upload_date else ""
    image_path = Path(IMAGE_DIR) / upload_date_str / encounter_file.filename
    
    if image_path.exists():
        return True, str(image_path)
    else:
        return False, str(image_path)

def check_direct_upload_exists(direct_image):
    """Check if a direct upload image exists on disk."""
    if not direct_image or not direct_image.filename:
        return False, "No filename in database record"
    
    # Check for edited version first, then original
    if direct_image.edited_filename:
        image_path = Path(DIRECT_UPLOAD_DIR) / direct_image.folder_rel / "edited" / direct_image.edited_filename
        filename = direct_image.edited_filename
    else:
        image_path = Path(DIRECT_UPLOAD_DIR) / direct_image.folder_rel / direct_image.filename
        filename = direct_image.filename
    
    if image_path.exists():
        return True, str(image_path)
    else:
        return False, str(image_path)

def check_grading_tasks(db_session):
    """Check all grading tasks for missing images."""
    print("\n=== CHECKING GRADING TASKS ===")
    
    grading_tasks = db_session.query(GradingTask).all()
    missing_tasks = []
    
    for task in grading_tasks:
        task_id = task.id
        task_uuid = task.uuid
        image_exists = False
        image_path = None
        image_type = None
        error_reason = None
        
        if task.encounter_file_id:
            # Check encounter file
            encounter_file = db_session.query(EncounterFile).filter(EncounterFile.id == task.encounter_file_id).first()
            image_exists, image_path = check_encounter_file_exists(encounter_file, db_session)
            image_type = "encounter_file"
            if not image_exists:
                error_reason = f"Encounter file ID {task.encounter_file_id} not found"
        
        elif task.direct_image_upload_id:
            # Check direct upload
            direct_image = db_session.query(DirectImageUpload).filter(DirectImageUpload.id == task.direct_image_upload_id).first()
            image_exists, image_path = check_direct_upload_exists(direct_image)
            image_type = "direct_upload"
            if not image_exists:
                error_reason = f"Direct upload ID {task.direct_image_upload_id} not found"
        
        if not image_exists:
            missing_tasks.append({
                'task_type': 'GradingTask',
                'task_id': task_id,
                'task_uuid': task_uuid,
                'image_type': image_type,
                'image_path': image_path,
                'error_reason': error_reason,
                'disease_id': task.disease_id,
                'lab_unit_id': task.lab_unit_id,
                'state': task.state
            })
            print(f"✗ Task {task_id} (UUID: {task_uuid}) - MISSING IMAGE")
            print(f"  Type: {image_type}")
            print(f"  Expected path: {image_path}")
            print(f"  Reason: {error_reason}")
        else:
            print(f"✓ Task {task_id} (UUID: {task_uuid}) - Image found")
    
    return missing_tasks

def check_intra_rater_tasks(db_session):
    """Check all intra-rater tasks for missing images."""
    print("\n=== CHECKING INTRA-RATER TASKS ===")
    
    intra_rater_tasks = db_session.query(IntraRaterTask).all()
    missing_tasks = []
    
    for task in intra_rater_tasks:
        task_id = task.id
        task_uuid = task.uuid
        image_exists = False
        image_path = None
        image_type = None
        error_reason = None
        
        if task.encounter_file_id:
            # Check encounter file
            encounter_file = db_session.query(EncounterFile).filter(EncounterFile.id == task.encounter_file_id).first()
            image_exists, image_path = check_encounter_file_exists(encounter_file, db_session)
            image_type = "encounter_file"
            if not image_exists:
                error_reason = f"Encounter file ID {task.encounter_file_id} not found"
        
        elif task.direct_image_upload_id:
            # Check direct upload
            direct_image = db_session.query(DirectImageUpload).filter(DirectImageUpload.id == task.direct_image_upload_id).first()
            image_exists, image_path = check_direct_upload_exists(direct_image)
            image_type = "direct_upload"
            if not image_exists:
                error_reason = f"Direct upload ID {task.direct_image_upload_id} not found"
        
        if not image_exists:
            missing_tasks.append({
                'task_type': 'IntraRaterTask',
                'task_id': task_id,
                'task_uuid': task.uuid,
                'image_type': image_type,
                'image_path': image_path,
                'error_reason': error_reason,
                'disease_id': task.disease_id,
                'lab_unit_id': task.lab_unit_id,
                'state': task.state
            })
            print(f"✗ Task {task_id} (UUID: {task_uuid}) - MISSING IMAGE")
            print(f"  Type: {image_type}")
            print(f"  Expected path: {image_path}")
            print(f"  Reason: {error_reason}")
        else:
            print(f"✓ Task {task_id} (UUID: {task_uuid}) - Image found")
    
    return missing_tasks

def main():
    """Main function to check for missing images."""
    print("Checking for missing image files in tasks...")
    print(f"IMAGE_DIR: {IMAGE_DIR}")
    print(f"DIRECT_UPLOAD_DIR: {DIRECT_UPLOAD_DIR}")
    
    # Create database session
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine)
    db_session = SessionLocal()
    
    try:
        # Check grading tasks
        grading_missing = check_grading_tasks(db_session)
        
        # Check intra-rater tasks
        intra_rater_missing = check_intra_rater_tasks(db_session)
        
        # Combine results
        all_missing = grading_missing + intra_rater_missing
        
        # Print summary
        print(f"\n=== SUMMARY ===")
        print(f"Total tasks with missing images: {len(all_missing)}")
        
        if all_missing:
            print(f"\nMissing tasks by type:")
            grading_count = len([t for t in all_missing if t['task_type'] == 'GradingTask'])
            intra_rater_count = len([t for t in all_missing if t['task_type'] == 'IntraRaterTask'])
            print(f"  GradingTask: {grading_count}")
            print(f"  IntraRaterTask: {intra_rater_count}")
            
            print(f"\nMissing tasks by image type:")
            encounter_count = len([t for t in all_missing if t['image_type'] == 'encounter_file'])
            direct_count = len([t for t in all_missing if t['image_type'] == 'direct_upload'])
            print(f"  Encounter files: {encounter_count}")
            print(f"  Direct uploads: {direct_count}")
            
            # Save detailed report to file
            report_file = Path("missing_images_report.txt")
            with open(report_file, 'w') as f:
                f.write("TASKS WITH MISSING IMAGE FILES\n")
                f.write("=" * 50 + "\n\n")
                
                for task in all_missing:
                    f.write(f"Task Type: {task['task_type']}\n")
                    f.write(f"Task ID: {task['task_id']}\n")
                    f.write(f"Task UUID: {task['task_uuid']}\n")
                    f.write(f"Image Type: {task['image_type']}\n")
                    f.write(f"Expected Path: {task['image_path']}\n")
                    f.write(f"Error Reason: {task['error_reason']}\n")
                    f.write(f"Disease ID: {task['disease_id']}\n")
                    f.write(f"Lab Unit ID: {task['lab_unit_id']}\n")
                    f.write(f"State: {task['state']}\n")
                    f.write("-" * 50 + "\n")
            
            print(f"\nDetailed report saved to: {report_file}")
            
            # Show first few missing tasks for quick reference
            print(f"\nFirst 5 missing tasks:")
            for i, task in enumerate(all_missing[:5]):
                print(f"{i+1}. Task {task['task_id']} ({task['task_type']}) - {task['error_reason']}")
        
        return all_missing
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return []
    finally:
        db_session.close()

if __name__ == "__main__":
    main()