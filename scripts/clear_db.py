#!/usr/bin/env python3
"""
Script to clear all data from the fundus image management database.
This will delete all images, encounters, gradings, tasks, jobs, and related data.
It also deletes all files in the /files directory and recreates essential directories.
"""

import sys
import os
import shutil
# Add the project root directory to the path so we can import models
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import Session, JobItem, Job, ZipFile, PatientEncounters, EncounterFile, EncounterFilePDF
from models import DiabeticRetinopathyReport, GlaucomaReport, GlaucomaResultsCleaned, ImageGrading
from models import DirectImageUpload, DirectImageVerify, GradingTask, Grade, Consensus
from models import AIGrade


def clear_files():
    """Clear all files in the /files directory."""
    files_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "files")
    
    if os.path.exists(files_dir):
        print(f"Clearing files from {files_dir}...")
        for item in os.listdir(files_dir):
            item_path = os.path.join(files_dir, item)
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


def recreate_directories():
    """Recreate essential directories in the /files directory."""
    files_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "files")
    
    # Define essential directories based on the application's needs
    essential_dirs = [
        "zip_upload_zips",      # For uploaded ZIP files
        "zips_upload_processed", # For processed ZIP files
        "zip_upload_processing_error", # For processing error ZIP files
        "zip_upload_images",     # For extracted images from ZIPs
        "direct_uploads",        # For direct image uploads
        "zip_upload_pdfs",       # For extracted PDFs from ZIPs
        "zip_dr_pdfs",          # For DR PDFs
        "zip_glaucoma_pdfs",    # For glaucoma PDFs
        "upload_meta"           # For upload metadata
    ]
    
    print("Recreating essential directories...")
    for dir_name in essential_dirs:
        dir_path = os.path.join(files_dir, dir_name)
        os.makedirs(dir_path, exist_ok=True)
        # Ensure the directory is empty by clearing it after creation
        for item in os.listdir(dir_path):
            item_path = os.path.join(dir_path, item)
            if os.path.isdir(item_path):
                shutil.rmtree(item_path)
                print(f"  Removed subdirectory: {dir_name}/{item}")
            else:
                os.remove(item_path)
                print(f"  Removed file: {dir_name}/{item}")
        print(f"  Created/Emptied directory: {dir_name}")
    
    print("Essential directories recreated successfully!")


def clear_database():
    """Clear all data from the database in the correct order."""
    db = Session()
    
    try:
        print("Starting to clear the database...")
        
        # Delete from tables with foreign key dependencies first
        print("Deleting AI Grades...")
        db.query(AIGrade).delete()
        
        print("Deleting Consensus...")
        db.query(Consensus).delete()
        
        print("Deleting Grades...")
        db.query(Grade).delete()
        
        print("Deleting Grading Tasks...")
        db.query(GradingTask).delete()
        
        print("Deleting Direct Image Verifications...")
        db.query(DirectImageVerify).delete()
        
        print("Deleting Image Gradings...")
        db.query(ImageGrading).delete()
        
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
        
        print("Deleting Job Items...")
        db.query(JobItem).delete()
        
        print("Deleting Jobs...")
        db.query(Job).delete()
        
        # Commit all deletions
        db.commit()
        print("Database cleared successfully!")
        
    except Exception as e:
        print(f"Error clearing database: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def reset_all():
    """Clear both database and files, then recreate essential directories."""
    clear_database()
    clear_files()
    recreate_directories()


if __name__ == "__main__":
    reset_all()