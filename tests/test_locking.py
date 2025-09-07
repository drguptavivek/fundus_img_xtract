#!/usr/bin/env python3
"""
Test script for the locking mechanism in the dual grading system.
"""

import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Session, EncounterFile, DirectImageUpload


def test_locking_mechanism():
    """Test the locking mechanism."""
    print("Testing locking mechanism...")
    
    # Get a session
    db = Session()
    
    try:
        # Test with EncounterFile
        encounter = db.query(EncounterFile).first()
        if encounter:
            print(f"Encounter file UUID: {encounter.uuid}")
            print(f"Initial lock status: is_locked = {encounter.is_locked}")
            
            # Lock the encounter
            encounter.is_locked = True
            db.add(encounter)
            db.commit()
            
            # Refresh and check
            db.refresh(encounter)
            print(f"Lock status after locking: is_locked = {encounter.is_locked}")
            
            # Unlock the encounter
            encounter.is_locked = False
            db.add(encounter)
            db.commit()
            
            # Refresh and check
            db.refresh(encounter)
            print(f"Lock status after unlocking: is_locked = {encounter.is_locked}")
        else:
            print("No encounter files found in database.")
            
        # Test with DirectImageUpload
        direct_upload = db.query(DirectImageUpload).first()
        if direct_upload:
            print(f"Direct upload UUID: {direct_upload.uuid}")
            print(f"Initial lock status: is_locked = {direct_upload.is_locked}")
            
            # Lock the direct upload
            direct_upload.is_locked = True
            db.add(direct_upload)
            db.commit()
            
            # Refresh and check
            db.refresh(direct_upload)
            print(f"Lock status after locking: is_locked = {direct_upload.is_locked}")
            
            # Unlock the direct upload
            direct_upload.is_locked = False
            db.add(direct_upload)
            db.commit()
            
            # Refresh and check
            db.refresh(direct_upload)
            print(f"Lock status after unlocking: is_locked = {direct_upload.is_locked}")
        else:
            print("No direct uploads found in database.")
            
        print("Test completed successfully.")
        
    except Exception as e:
        print(f"Error during test: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    test_locking_mechanism()