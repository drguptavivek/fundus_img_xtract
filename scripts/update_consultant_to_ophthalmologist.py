#!/usr/bin/env python3
"""
Script to update all consultant gradings to ophthalmologist in the database.
"""

import os
import sys
import argparse
from pathlib import Path

# Add the project root to the path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

# Import after adding project root to path
from models import Session, ImageGrading

def update_consultant_to_ophthalmologist():
    """
    Update all gradings with grader_role='consultant' to grader_role='ophthalmologist'.
    """
    db = Session()
    try:
        # Find all gradings where grader_role is 'consultant'
        gradings_to_update = db.query(ImageGrading).filter(
            ImageGrading.grader_role == 'consultant'
        ).all()
        
        print(f"Found {len(gradings_to_update)} gradings to update")
        
        # Update the gradings
        updated_count = 0
        for grading in gradings_to_update:
            print(f"Updating grading {grading.id}: changing grader_role from 'consultant' to 'ophthalmologist'")
            grading.grader_role = 'ophthalmologist'
            updated_count += 1
            
        db.commit()
        print(f"Successfully updated {updated_count} gradings")
        return True
        
    except Exception as e:
        print(f"Error updating gradings: {e}")
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
        ophthalmologist_gradings = db.query(ImageGrading).filter(ImageGrading.grader_role == 'ophthalmologist').count()
        ophthalmologist_gradings = db.query(ImageGrading).filter(ImageGrading.grader_role == 'ophthalmologist').count()
        resident_gradings = db.query(ImageGrading).filter(ImageGrading.grader_role == 'resident').count()
        admin_gradings = db.query(ImageGrading).filter(ImageGrading.grader_role == 'admin').count()
        
        print(f"\n--- Grading Statistics ---")
        print(f"Total gradings: {total_gradings}")
        print(f"Consultant gradings: {consultant_gradings}")
        print(f"Ophthalmologist gradings: {ophthalmologist_gradings}")
        print(f"Resident gradings: {resident_gradings}")
        print(f"Admin gradings: {admin_gradings}")
        
    finally:
        db.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Update consultant gradings to ophthalmologist")
    parser.add_argument("--force", action="store_true", help="Run without confirmation prompt")
    args = parser.parse_args()
    
    print("=== Consultant to Ophthalmologist Grading Update Script ===")
    
    # Show statistics before update
    print("\nBefore update:")
    show_statistics()
    
    # Check if we should proceed without confirmation
    if not args.force:
        print("\nThis script will update all gradings with grader_role='consultant' to grader_role='ophthalmologist'")
        
        try:
            response = input("\nDo you want to proceed? (yes/no): ")
            if response.lower() not in ['yes', 'y']:
                print("Operation cancelled.")
                sys.exit(0)
        except EOFError:
            print("\nOperation cancelled (no input available).")
            sys.exit(0)
    
    # Perform the update
    success = update_consultant_to_ophthalmologist()
    
    if success:
        print("\nAfter update:")
        show_statistics()
        print("\nUpdate completed successfully!")
    else:
        print("\nUpdate failed!")
        sys.exit(1)