#!/usr/bin/env python3
"""
Script to delete tasks with missing image files and their associated grades.
This should be used with caution as it will permanently delete data.
"""

import os
import sys
from pathlib import Path
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine

# Add parent directory to path to import models
sys.path.append(str(Path(__file__).parent.parent))

from models import (
    Base, 
    GradingTask, 
    IntraRaterTask,
    Grade,
    IntraRaterGrade,
    Session as DBSession,
    DATABASE_URL
)

def delete_grading_task_and_grades(task_id, db_session):
    """Delete a grading task and all its associated grades."""
    print(f"Deleting GradingTask {task_id} and associated grades...")
    
    # First delete all grades associated with this task
    deleted_grades = db_session.query(Grade).filter(Grade.task_id == task_id).delete()
    print(f"  Deleted {deleted_grades} grades")
    
    # Then delete the task itself
    deleted_task = db_session.query(GradingTask).filter(GradingTask.id == task_id).delete()
    print(f"  Deleted task: {deleted_task}")
    
    return deleted_grades > 0 or deleted_task > 0

def delete_intra_rater_task_and_grades(task_id, db_session):
    """Delete an intra-rater task and all its associated grades."""
    print(f"Deleting IntraRaterTask {task_id} and associated grades...")
    
    # First delete all grades associated with this task
    deleted_grades = db_session.query(IntraRaterGrade).filter(IntraRaterGrade.task_id == task_id).delete()
    print(f"  Deleted {deleted_grades} intra-rater grades")
    
    # Then delete the task itself
    deleted_task = db_session.query(IntraRaterTask).filter(IntraRaterTask.id == task_id).delete()
    print(f"  Deleted task: {deleted_task}")
    
    return deleted_grades > 0 or deleted_task > 0

def main():
    """Main function to delete tasks with missing images."""
    print("DELETING TASKS WITH MISSING IMAGE FILES")
    print("=" * 50)
    print("WARNING: This will permanently delete tasks and their grades!")
    print("=" * 50)
    
    # Tasks with missing images identified from previous analysis
    missing_tasks = [
        {'task_type': 'GradingTask', 'task_id': 39, 'reason': 'Encounter file ID 72 not found'},
        {'task_type': 'GradingTask', 'task_id': 40, 'reason': 'Encounter file ID 73 not found'},
        {'task_type': 'GradingTask', 'task_id': 41, 'reason': 'Encounter file ID 74 not found'},
        {'task_type': 'GradingTask', 'task_id': 42, 'reason': 'Encounter file ID 75 not found'},
        {'task_type': 'IntraRaterTask', 'task_id': 11, 'reason': 'No image reference (both encounter_file_id and direct_image_upload_id are None)'},
    ]
    
    # Create database session
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine)
    db_session = SessionLocal()
    
    try:
        # Ask for confirmation
        print("\nTasks to be deleted:")
        for task in missing_tasks:
            print(f"  {task['task_type']} ID {task['task_id']}: {task['reason']}")
        
        print("\nType 'DELETE' to confirm deletion, or anything else to cancel:")
        confirmation = input().strip()
        
        if confirmation.upper() != 'DELETE':
            print("Operation cancelled.")
            return
        
        print("\nProceeding with deletion...")
        
        total_deleted = 0
        for task in missing_tasks:
            if task['task_type'] == 'GradingTask':
                if delete_grading_task_and_grades(task['task_id'], db_session):
                    total_deleted += 1
            elif task['task_type'] == 'IntraRaterTask':
                if delete_intra_rater_task_and_grades(task['task_id'], db_session):
                    total_deleted += 1
        
        # Commit all deletions
        db_session.commit()
        
        print(f"\nDeletion complete. Total tasks deleted: {total_deleted}")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        db_session.rollback()
    finally:
        db_session.close()

if __name__ == "__main__":
    main()