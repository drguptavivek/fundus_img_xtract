#!/usr/bin/env python3
"""
Script to clean up the test admin user created by create_test_admin.py
"""

import sys
from pathlib import Path

# Add the project root to the path
file_path = Path(__file__).resolve()
project_root = file_path.parent.parent
sys.path.insert(0, str(project_root))

try:
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import select
    from sqlalchemy.exc import SQLAlchemyError
    from models import engine, User, Role
except ModuleNotFoundError as e:
    print(f"Error importing modules: {e}", file=sys.stderr)
    sys.exit(1)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

def cleanup_test_admin():
    """Remove the test admin user"""
    username = "Test"
    
    with SessionLocal() as db:
        # Find the user
        user = db.execute(
            select(User).where(User.username.ilike(username))
        ).scalar_one_or_none()
        
        if not user:
            print(f"User '{username}' not found.")
            return True
        
        # Check for any related data that might prevent deletion
        # This is a safety check to avoid breaking referential integrity
        related_data = []
        
        # Check for uploads
        if hasattr(user, 'direct_uploads') and user.direct_uploads:
            related_data.append(f"{len(user.direct_uploads)} direct image uploads")
        
        # Check for grading tasks
        if hasattr(user, 'grading_tasks') and user.grading_tasks:
            related_data.append(f"{len(user.grading_tasks)} grading tasks")
        
        # Check for jobs
        if hasattr(user, 'jobs') and user.jobs:
            related_data.append(f"{len(user.jobs)} jobs")
        
        if related_data:
            print(f"Cannot delete user '{username}' - they have related data:")
            for item in related_data:
                print(f"  - {item}")
            print("Please clean up this data first or use a more specific deletion script.")
            return False
        
        # Remove the user
        try:
            db.delete(user)
            db.commit()
            print(f"Successfully deleted user '{username}'.")
            return True
        except SQLAlchemyError as e:
            print(f"Database error while deleting user: {e}", file=sys.stderr)
            db.rollback()
            return False

def force_cleanup_test_admin():
    """Force remove the test admin user and their related data"""
    username = "Test"
    
    with SessionLocal() as db:
        # Find the user
        user = db.execute(
            select(User).where(User.username.ilike(username))
        ).scalar_one_or_none()
        
        if not user:
            print(f"User '{username}' not found.")
            return True
        
        # Get counts before deletion
        upload_count = len(user.direct_uploads) if hasattr(user, 'direct_uploads') else 0
        task_count = len(user.grading_tasks) if hasattr(user, 'grading_tasks') else 0
        job_count = len(user.jobs) if hasattr(user, 'jobs') else 0
        
        # Remove the user (cascade should handle related data)
        try:
            db.delete(user)
            db.commit()
            print(f"Force deleted user '{username}' and related data:")
            if upload_count > 0:
                print(f"  - {upload_count} direct image uploads")
            if task_count > 0:
                print(f"  - {task_count} grading tasks")
            if job_count > 0:
                print(f"  - {job_count} jobs")
            return True
        except SQLAlchemyError as e:
            print(f"Database error while deleting user: {e}", file=sys.stderr)
            db.rollback()
            return False

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Clean up test admin user")
    parser.add_argument("--force", action="store_true", 
                       help="Force delete user and all related data")
    
    args = parser.parse_args()
    
    try:
        if args.force:
            success = force_cleanup_test_admin()
        else:
            success = cleanup_test_admin()
        
        if success:
            print("Cleanup completed successfully!")
        else:
            print("Cleanup failed. Use --force to delete user and all related data.", file=sys.stderr)
            sys.exit(1)
    except SQLAlchemyError as e:
        print(f"Database error: {e}", file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(3)