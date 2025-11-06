#!/usr/bin/env python3
"""
Script to check the source image path for a given UUID.
This helps debug 404 errors for missing images.
"""

import sys
import os
from pathlib import Path

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import (
    DirectImageUpload,
    EncounterFile,
    PatientEncounters,
    ZipFile,
    DIRECT_UPLOAD_DIR,
    IMAGE_DIR,
    BASE_DIR
)
from db_transaction_manager import get_db_session
import os

def check_image_uuid(uuid_str: str):
    """Check the database for a UUID and show the expected file path."""
    print(f"Checking UUID: {uuid_str}")
    print("=" * 60)
    
    with get_db_session() as db:
        # Check DirectImageUpload table
        direct_image = db.query(DirectImageUpload).filter(DirectImageUpload.uuid == uuid_str).first()
        if direct_image:
            print("✓ Found in DirectImageUpload table")
            print(f"  - ID: {direct_image.id}")
            print(f"  - Filename: {direct_image.filename}")
            print(f"  - Folder: {direct_image.folder_rel}")
            print(f"  - Edited Filename: {direct_image.edited_filename}")
            print(f"  - Created At: {direct_image.created_at}")
            print(f"  - Lab Unit: {direct_image.lab_unit.name if direct_image.lab_unit else 'N/A'}")
            print(f"  - Hospital: {direct_image.hospital.name if direct_image.hospital else 'N/A'}")
            
            # Calculate expected paths
            original_path = DIRECT_UPLOAD_DIR / direct_image.folder_rel / direct_image.filename
            edited_path = DIRECT_UPLOAD_DIR / direct_image.folder_rel / "edited" / direct_image.edited_filename if direct_image.edited_filename else None
            
            print(f"\nExpected file paths:")
            print(f"  - Original: {original_path}")
            print(f"    Exists: {original_path.exists()}")
            
            if edited_path:
                print(f"  - Edited: {edited_path}")
                print(f"    Exists: {edited_path.exists()}")
            
            # Check which file should be served
            if direct_image.edited_filename and edited_path and edited_path.exists():
                print(f"\n→ Would serve: EDITED version")
            elif original_path.exists():
                print(f"\n→ Would serve: ORIGINAL version")
            else:
                print(f"\n→ ERROR: No files found on disk!")
            
            return
        
        # Check EncounterFile table
        encounter_file = db.query(EncounterFile).filter(EncounterFile.uuid == uuid_str).first()
        if encounter_file:
            print("✓ Found in EncounterFile table")
            print(f"  - ID: {encounter_file.id}")
            print(f"  - Filename: {encounter_file.filename}")
            print(f"  - Eye Side: {encounter_file.eye_side}")
            
            # Get patient encounter info
            if encounter_file.patient_encounter:
                pe = encounter_file.patient_encounter
                print(f"  - Patient ID: {pe.patient_id}")
                print(f"  - Name: {pe.name}")
                print(f"  - Capture Date: {pe.capture_date_dt}")
                
                if pe.zip_file:
                    print(f"  - Zip File Upload Date: {pe.zip_file.upload_date}")
                    
                    # Calculate expected path
                    upload_date_str = pe.zip_file.upload_date.strftime("%Y_%m_%d") if pe.zip_file.upload_date else ""
                    image_path = IMAGE_DIR / upload_date_str / encounter_file.filename
                    
                    print(f"\nExpected file path:")
                    print(f"  - Path: {image_path}")
                    print(f"  - Exists: {image_path.exists()}")
                    
                    if image_path.exists():
                        print(f"\n→ Would serve: ENCOUNTER file")
                    else:
                        print(f"\n→ ERROR: File not found on disk!")
                else:
                    print(f"\n→ ERROR: No zip file associated with patient encounter!")
            else:
                print(f"\n→ ERROR: No patient encounter associated with encounter file!")
            
            return
        
        # If we reach here, UUID was not found
        print("✗ UUID not found in either DirectImageUpload or EncounterFile tables")
        print("\nSuggestions:")
        print("  1. Check if the UUID is correct")
        print("  2. The image might have been deleted from the database")
        print("  3. There might be a database integrity issue")

def check_media_directories():
    """Check if media directories exist and are accessible."""
    print("\nMedia Directory Status:")
    print("=" * 60)
    
    print(f"DIRECT_UPLOAD_DIR: {DIRECT_UPLOAD_DIR}")
    print(f"  Exists: {DIRECT_UPLOAD_DIR.exists()}")
    print(f"  Readable: {os.access(DIRECT_UPLOAD_DIR, os.R_OK) if DIRECT_UPLOAD_DIR.exists() else 'N/A'}")
    
    print(f"\nIMAGE_DIR: {IMAGE_DIR}")
    print(f"  Exists: {IMAGE_DIR.exists()}")
    print(f"  Readable: {os.access(IMAGE_DIR, os.R_OK) if IMAGE_DIR.exists() else 'N/A'}")
    
    print(f"\nBASE_DIR: {BASE_DIR}")
    print(f"  Exists: {BASE_DIR.exists()}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python check_image_uuid.py <uuid>")
        print("Example: python check_image_uuid.py c0d3b563-c6b7-4df8-b7bd-44ef1471479a")
        sys.exit(1)
    
    uuid_to_check = sys.argv[1]
    
    # Check media directories first
    check_media_directories()
    
    print("\n")
    
    # Check the specific UUID
    check_image_uuid(uuid_to_check)