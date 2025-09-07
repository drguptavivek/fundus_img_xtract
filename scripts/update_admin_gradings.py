#!/usr/bin/env python3
"""
One-time script to update all existing admin gradings to ophthalmologist 
for users who have both admin and ophthalmologist roles.
"""

import os
import sys
import argparse
from pathlib import Path

# Add the project root to the path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

# Import after adding project root to path
from models import Session, ImageGrading, User, Role
from sqlalchemy import and_, or_

def update_admin_gradings_to_ophthalmologist():
    """
    Update all existing admin gradings to ophthalmologist 
    for users who have both admin and ophthalmologist roles.
    """
    db = Session()
    try:
        # Get the role IDs for admin and ophthalmologist
        admin_role = db.query(Role).filter(Role.name == 'admin').first()
        ophthalmologist_role = db.query(Role).filter(Role.name == 'ophthalmologist').first()
        
        if not admin_role or not ophthalmologist_role:
            print("Error: Could not find admin or ophthalmologist role")
            return False
            
        # Get users who have both admin and ophthalmologist roles
        users_with_both_roles = db.query(User).filter(
            and_(
                User.roles.any(Role.id == admin_role.id),
                User.roles.any(Role.id == ophthalmologist_role.id)
            )
        ).all()
        
        user_ids = [user.id for user in users_with_both_roles]
        print(f"Found {len(user_ids)} users with both admin and ophthalmologist roles")
        
        if not user_ids:
            print("No users found with both roles. Nothing to update.")
            return True
            
        # Find all gradings where:
        # 1. The grader_user_id is in our list of users with both roles
        # 2. The grader_role is 'admin'
        gradings_to_update = db.query(ImageGrading).filter(
            and_(
                ImageGrading.grader_user_id.in_(user_ids),
                ImageGrading.grader_role == 'admin'
            )
        ).all()
        
        print(f"Found {len(gradings_to_update)} gradings to update")
        
        # Update the gradings
        updated_count = 0
        for grading in gradings_to_update:
            print(f"Updating grading {grading.id}: changing grader_role from 'admin' to 'consultant'")
            grading.grader_role = 'consultant'
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
    Show statistics about gradings before and after the update.
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
        
        # Show users with both roles
        admin_role = db.query(Role).filter(Role.name == 'admin').first()
        ophthalmologist_role = db.query(Role).filter(Role.name == 'ophthalmologist').first()
        
        if admin_role and ophthalmologist_role:
            users_with_both = db.query(User).filter(
                and_(
                    User.roles.any(Role.id == admin_role.id),
                    User.roles.any(Role.id == ophthalmologist_role.id)
                )
            ).count()
            print(f"Users with both admin and ophthalmologist roles: {users_with_both}")
        
    finally:
        db.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Update admin gradings to ophthalmologist for users with both roles")
    parser.add_argument("--force", action="store_true", help="Run without confirmation prompt")
    args = parser.parse_args()
    
    print("=== Admin to Ophthalmologist Grading Update Script ===")
    
    # Show statistics before update
    print("\nBefore update:")
    show_statistics()
    
    # Check if we should proceed without confirmation
    if not args.force:
        print("\nThis script will update all gradings with grader_role='admin' to grader_role='consultant'")
        print("for users who have both admin and ophthalmologist roles.")
        
        try:
            response = input("\nDo you want to proceed? (yes/no): ")
            if response.lower() not in ['yes', 'y']:
                print("Operation cancelled.")
                sys.exit(0)
        except EOFError:
            print("\nOperation cancelled (no input available).")
            sys.exit(0)
    
    # Perform the update
    success = update_admin_gradings_to_ophthalmologist()
    
    if success:
        print("\nAfter update:")
        show_statistics()
        print("\nUpdate completed successfully!")
    else:
        print("\nUpdate failed!")
        sys.exit(1)