#!/usr/bin/env python3
"""
Backup script to revert the admin to ophthalmologist grading update.
This script can be used to restore the original grader_role values if needed.
"""

import os
import sys
import argparse
import json
from datetime import datetime
from pathlib import Path

# Add the project root to the path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

# Import after adding project root to path
from models import Session, ImageGrading, User, Role
from sqlalchemy import and_, or_

def backup_current_state(backup_file=None):
    """
    Create a backup of the current grading state.
    """
    if backup_file is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = f"grading_backup_{timestamp}.json"
    
    db = Session()
    try:
        # Get all gradings with their current state
        gradings = db.query(ImageGrading).all()
        
        backup_data = []
        for grading in gradings:
            backup_data.append({
                "id": grading.id,
                "grader_user_id": grading.grader_user_id,
                "grader_role": grading.grader_role,
                "graded_for": grading.graded_for,
                "impression": grading.impression,
                "created_at": grading.created_at.isoformat() if grading.created_at else None,
                "updated_at": grading.updated_at.isoformat() if grading.updated_at else None
            })
        
        # Write to file
        with open(backup_file, 'w') as f:
            json.dump(backup_data, f, indent=2)
        
        print(f"Backup created: {backup_file}")
        print(f"Backed up {len(backup_data)} gradings")
        return backup_file
    except Exception as e:
        print(f"Error creating backup: {e}")
        return None
    finally:
        db.close()

def restore_from_backup(backup_file):
    """
    Restore grading state from a backup file.
    """
    if not os.path.exists(backup_file):
        print(f"Backup file not found: {backup_file}")
        return False
    
    try:
        with open(backup_file, 'r') as f:
            backup_data = json.load(f)
    except Exception as e:
        print(f"Error reading backup file: {e}")
        return False
    
    db = Session()
    try:
        restored_count = 0
        for item in backup_data:
            grading = db.query(ImageGrading).filter(ImageGrading.id == item["id"]).first()
            if grading:
                grading.grader_role = item["grader_role"]
                restored_count += 1
        
        db.commit()
        print(f"Restored {restored_count} gradings from backup")
        return True
    except Exception as e:
        print(f"Error restoring from backup: {e}")
        db.rollback()
        return False
    finally:
        db.close()

def show_statistics():
    """
    Show statistics about gradings.
    """
    db = Session()
    try:
        # Get statistics about gradings
        total_gradings = db.query(ImageGrading).count()
        admin_gradings = db.query(ImageGrading).filter(ImageGrading.grader_role == 'admin').count()
        consultant_gradings = db.query(ImageGrading).filter(ImageGrading.grader_role == 'ophthalmologist').count()
        
        print(f"\n--- Grading Statistics ---")
        print(f"Total gradings: {total_gradings}")
        print(f"Admin gradings: {admin_gradings}")
        print(f"Consultant gradings: {consultant_gradings}")
        
    finally:
        db.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backup or restore grading data")
    parser.add_argument("--backup", action="store_true", help="Create a backup of current grading state")
    parser.add_argument("--restore", type=str, help="Restore from a backup file")
    parser.add_argument("--backup-file", type=str, help="Backup file path (for backup or restore)")
    parser.add_argument("--force", action="store_true", help="Run without confirmation prompt")
    
    args = parser.parse_args()
    
    if args.backup:
        backup_file = backup_current_state(args.backup_file)
        if backup_file:
            print(f"Backup completed successfully: {backup_file}")
        else:
            print("Backup failed!")
            sys.exit(1)
    elif args.restore:
        if not args.force:
            print(f"This will restore grading data from {args.restore}")
            print("This operation cannot be undone!")
            try:
                response = input("\nDo you want to proceed? (yes/no): ")
                if response.lower() not in ['yes', 'y']:
                    print("Operation cancelled.")
                    sys.exit(0)
            except EOFError:
                print("\nOperation cancelled (no input available).")
                sys.exit(0)
        
        success = restore_from_backup(args.restore)
        if success:
            print("Restore completed successfully!")
        else:
            print("Restore failed!")
            sys.exit(1)
    else:
        # Show current statistics
        show_statistics()