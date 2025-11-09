#!/usr/bin/env python3
"""
Script to clear ALL data from the fundus image management database.

USAGE:
    uv run scripts/clear_db.py

DESCRIPTION:
This will delete ALL data including:
- Images, encounters, gradings, tasks, jobs, and related data
- User management data (users, roles, permissions)
- Reference data (hospitals, lab units, diseases, cameras, areas)
- Security data (login attempts, IP locks, password reset attempts)
- Notifications and sessions
- Application settings and viewer preferences
- AI models and intra-rater reliability data

It also deletes all files in the /files directory, clears all log files in the /logs directory,
and recreates essential directories based on environment variables defined in .env file.

WARNING: This is a complete database reset. All data will be permanently lost.
Make sure you have backups if needed before running this script.
"""

import sys
import os
import shutil
# Add the project root directory to the path so we can import models
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import (
    # Import all models for complete database clearing
    # Viewer settings and presets
    ViewerPresets, ViewerSettings,
    # Session management
    FlaskSession,
    # Intra-rater reliability
    IntraRaterGrade, IntraRaterTask, IntraRaterBatch,
    # Application settings
    AppSetting,
    # Ad-hoc task creation
    AdHocTaskCreation,
    # Notifications
    NotificationRead, Notification,
    # Task tracking
    TaskTracker,
    # User role management
    UserDiseaseUnitRole,
    # AI models
    AIModel,
    # Security
    PasswordResetAttempt, IpLock, LoginAttempt,
    # Reference data
    GradingsFeatures, DiseaseGrading, Area, Disease, Camera, LabUnit, Hospital,
    # User management
    UserRole, Role, User,
    # Image and grading data
    Consensus, Grade, GradingTask, DirectImageVerify, DirectImageUpload,
    GlaucomaResultsCleaned, GlaucomaReport, DiabeticRetinopathyReport,
    EncounterFilePDF, EncounterFile, PatientEncounters, ZipFile,
    JobItem, Job
)

from utils.env_loader import load_environment
load_environment()

def clear_files():
    """Clear all files in the files directory."""
    from dotenv import load_dotenv
    from pathlib import Path
    
    # Load environment variables and get BASE_DIR like in models.py
    BASE_DIR = Path(__file__).resolve().parent.parent
    files_dir = BASE_DIR / "files"
    
    if os.path.exists(files_dir):
        print(f"Clearing files from {files_dir}...")
        for item in os.listdir(files_dir):
            item_path = files_dir / item
            if os.path.isdir(item_path):
                shutil.rmtree(item_path)
                print(f"  Deleted directory: {item}")
            else:
                os.remove(item_path)
                print(f"  Deleted file: {item}")
        print("Files cleared successfully!")
    else:
        print("Files directory does not exist, creating it...")
        os.makedirs(files_dir)


def clear_logs():
    """Clear all log files in the logs directory."""
    from pathlib import Path
    
    BASE_DIR = Path(__file__).resolve().parent.parent
    logs_dir = BASE_DIR / "logs"
    
    if os.path.exists(logs_dir):
        print(f"Clearing log files from {logs_dir}...")
        for item in os.listdir(logs_dir):
            item_path = logs_dir / item
            if os.path.isdir(item_path):
                shutil.rmtree(item_path)
                print(f"  Deleted log directory: {item}")
            else:
                os.remove(item_path)
                print(f"  Deleted log file: {item}")
        print("Log files cleared successfully!")
    else:
        print("Logs directory does not exist, creating it...")
        os.makedirs(logs_dir)


def recreate_directories():
    """Recreate essential directories based on environment variables."""
    from pathlib import Path
    
    # Load environment variables
    BASE_DIR = Path(__file__).resolve().parent.parent
    
    # Define essential directories based on environment variables from models.py
    essential_dirs = [
        os.getenv("UPLOAD_DIR", "files/zip_upload_zips"),
        os.getenv("PROCESSED_DIR", "files/zips_upload_processed"),
        os.getenv("PROCESSING_ERROR_DIR", "files/zip_upload_processing_error"),
        os.getenv("IMAGE_DIR", "files/zip_upload_images"),
        os.getenv("DIRECT_UPLOAD_DIR", "files/direct_uploads"),
        os.getenv("PDF_DIR", "files/zip_upload_pdfs"),
        os.getenv("DR_PDF_DIR", "files/dr_pdfs"),
        os.getenv("GLAUCOMA_PDF_DIR", "files/glaucoma_pdfs"),
        "files/upload_meta"  # For upload metadata (not in env vars)
    ]
    
    print("Recreating essential directories...")
    for dir_path in essential_dirs:
        # Convert to absolute path
        full_dir_path = BASE_DIR / dir_path
        
        # Create directory if it doesn't exist
        os.makedirs(full_dir_path, exist_ok=True)
        
        # Ensure the directory is empty by clearing it after creation
        if os.path.exists(full_dir_path):
            for item in os.listdir(full_dir_path):
                item_path = full_dir_path / item
                if os.path.isdir(item_path):
                    shutil.rmtree(item_path)
                    print(f"  Removed subdirectory: {dir_path}/{item}")
                else:
                    os.remove(item_path)
                    print(f"  Removed file: {dir_path}/{item}")
        
        print(f"  Created/Emptied directory: {dir_path}")
    
    print("Essential directories recreated successfully!")


def clear_database():
    """Clear all data from the database in the correct order."""
    from utils.utils import get_db_session
    
    with get_db_session() as db:
        try:
            print("Starting to clear the database...")

            # Clear viewer settings and presets (user-specific data)
            print("Deleting Viewer Presets...")
            db.query(ViewerPresets).delete()

            print("Deleting Viewer Settings...")
            db.query(ViewerSettings).delete()

            # Clear session management
            print("Deleting Flask Sessions...")
            db.query(FlaskSession).delete()

            # Clear intra-rater reliability data (depends on tasks, users, etc.)
            print("Deleting Intra-Rater Grades...")
            db.query(IntraRaterGrade).delete()

            print("Deleting Intra-Rater Tasks...")
            db.query(IntraRaterTask).delete()

            print("Deleting Intra-Rater Batches...")
            db.query(IntraRaterBatch).delete()

            # Clear application settings
            print("Deleting Application Settings...")
            db.query(AppSetting).delete()

            # Clear ad-hoc task creation records
            print("Deleting Ad-Hoc Task Creations...")
            db.query(AdHocTaskCreation).delete()
        
            # Clear notifications
            print("Deleting Notification Reads...")
            db.query(NotificationRead).delete()
            
            print("Deleting Notifications...")
            db.query(Notification).delete()
            
            # Clear task tracking
            print("Deleting Task Trackers...")
            db.query(TaskTracker).delete()
            
            # Clear user role management
            print("Deleting User Disease Unit Roles...")
            db.query(UserDiseaseUnitRole).delete()
            
            # Clear AI models (referenced by grades)
            print("Deleting AI Models...")
            db.query(AIModel).delete()
            
            # Clear security-related data
            print("Deleting Password Reset Attempts...")
            db.query(PasswordResetAttempt).delete()
            
            print("Deleting IP Locks...")
            db.query(IpLock).delete()
            
            print("Deleting Login Attempts...")
            db.query(LoginAttempt).delete()
            
            # Clear grading consensus and grades (depend on tasks)
            print("Deleting Consensus...")
            db.query(Consensus).delete()
            
            print("Deleting Grades...")
            db.query(Grade).delete()
            
            # Clear grading tasks (depend on images, diseases, etc.)
            print("Deleting Grading Tasks...")
            db.query(GradingTask).delete()
            
            # Clear image-related data
            print("Deleting Direct Image Verifications...")
            db.query(DirectImageVerify).delete()

            # Note: ImageGrading model removed - now using Grade model through GradingTask
            print("Deleting Direct Image Uploads...")
            db.query(DirectImageUpload).delete()
            
            print("Deleting Glaucoma Results Cleaned...")
            db.query(GlaucomaResultsCleaned).delete()
            
            print("Deleting Glaucoma Reports...")
            db.query(GlaucomaReport).delete()
            
            print("Deleting Diabetic Retinopathy Reports...")
            db.query(DiabeticRetinopathyReport).delete()
            
            print("Deleting Encounter File PDFs...")
            db.query(EncounterFilePDF).delete()
            
            print("Deleting Encounter Files...")
            db.query(EncounterFile).delete()
            
            print("Deleting Patient Encounters...")
            db.query(PatientEncounters).delete()
            
            print("Deleting Zip Files...")
            db.query(ZipFile).delete()
            
            # Clear job-related data
            print("Deleting Job Items...")
            db.query(JobItem).delete()
            
            print("Deleting Jobs...")
            db.query(Job).delete()
            
            # Clear reference data (after dependent data is deleted)
            print("Deleting Gradings Features...")
            db.query(GradingsFeatures).delete()
            
            print("Deleting Disease Gradings...")
            db.query(DiseaseGrading).delete()
            
            print("Deleting Areas...")
            db.query(Area).delete()
            
            print("Deleting Diseases...")
            db.query(Disease).delete()
            
            print("Deleting Cameras...")
            db.query(Camera).delete()
            
            print("Deleting Lab Units...")
            db.query(LabUnit).delete()
            
            print("Deleting Hospitals...")
            db.query(Hospital).delete()
            
            # Clear user management (after dependent data is deleted)
            print("Deleting User Roles...")
            db.query(UserRole).delete()
            
            print("Deleting Roles...")
            db.query(Role).delete()
            
            print("Deleting Users...")
            db.query(User).delete()
            
            # Commit all deletions
            db.commit()
            print("Database cleared successfully!")
        
        except Exception as e:
                print(f"Error clearing database: {e}")
                db.rollback()
                raise


def reset_all():
    """Clear both database and files, then recreate essential directories."""
    # Add confirmation step to prevent accidental data loss
    print("=" * 60)
    print("WARNING: This will completely reset the database and file system!")
    print("This action will permanently delete:")
    print("  - ALL database records (users, images, gradings, etc.)")
    print("  - ALL uploaded files and directories")
    print("  - ALL application settings and preferences")
    print("  - ALL log files and directories")
    print("=" * 60)
    
    # Get user confirmation
    confirmation = input("Type 'DELETE ALL DATA' to confirm this action: ")
    
    if confirmation != "DELETE ALL DATA":
        print("Operation cancelled. No data was deleted.")
        return
    
    print("\nConfirmation received. Starting database and file reset...")
    print("=" * 60)
    
    try:
        clear_database()
        clear_files()
        clear_logs()
        recreate_directories()
        print("=" * 60)
        print("SUCCESS: Database, file system, and logs reset completed!")
        print("=" * 60)
    except Exception as e:
        print("=" * 60)
        print(f"ERROR: Reset failed with error: {e}")
        print("Please check the error message above and try again.")
        print("=" * 60)
        raise


if __name__ == "__main__":
    reset_all()