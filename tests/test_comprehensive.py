#!/usr/bin/env python3
"""
Comprehensive test script for the dual grading system.
"""

import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Session, EncounterFile, DirectImageUpload, ImageGrading


def test_comprehensive_system():
    """Test the comprehensive dual grading system."""
    print("Testing comprehensive dual grading system...")
    
    # Get a session
    db = Session()
    
    try:
        # Test with EncounterFile
        encounter = db.query(EncounterFile).first()
        if encounter:
            print(f"Encounter file UUID: {encounter.uuid}")
            print(f"Initial status - locked: {encounter.is_locked}, arbitrated: {encounter.is_arbitration}")
            
            # Test locking mechanism
            encounter.is_locked = True
            encounter.is_arbitration = False
            db.add(encounter)
            db.commit()
            
            # Refresh and check
            db.refresh(encounter)
            print(f"After locking - locked: {encounter.is_locked}, arbitrated: {encounter.is_arbitration}")
            
            # Test unlocking
            encounter.is_locked = False
            db.add(encounter)
            db.commit()
            
            # Refresh and check
            db.refresh(encounter)
            print(f"After unlocking - locked: {encounter.is_locked}, arbitrated: {encounter.is_arbitration}")
            
            # Test arbitration
            encounter.is_arbitration = True
            db.add(encounter)
            db.commit()
            
            # Refresh and check
            db.refresh(encounter)
            print(f"After arbitration - locked: {encounter.is_locked}, arbitrated: {encounter.is_arbitration}")
        else:
            print("No encounter files found in database.")
            
        # Test with DirectImageUpload
        direct_upload = db.query(DirectImageUpload).first()
        if direct_upload:
            print(f"Direct upload UUID: {direct_upload.uuid}")
            print(f"Initial status - locked: {direct_upload.is_locked}, arbitrated: {direct_upload.is_arbitration}")
            
            # Test locking mechanism
            direct_upload.is_locked = True
            direct_upload.is_arbitration = False
            db.add(direct_upload)
            db.commit()
            
            # Refresh and check
            db.refresh(direct_upload)
            print(f"After locking - locked: {direct_upload.is_locked}, arbitrated: {direct_upload.is_arbitration}")
            
            # Test unlocking
            direct_upload.is_locked = False
            db.add(direct_upload)
            db.commit()
            
            # Refresh and check
            db.refresh(direct_upload)
            print(f"After unlocking - locked: {direct_upload.is_locked}, arbitrated: {direct_upload.is_arbitration}")
            
            # Test arbitration
            direct_upload.is_arbitration = True
            db.add(direct_upload)
            db.commit()
            
            # Refresh and check
            db.refresh(direct_upload)
            print(f"After arbitration - locked: {direct_upload.is_locked}, arbitrated: {direct_upload.is_arbitration}")
        else:
            print("No direct uploads found in database.")
            
        print("Comprehensive test completed successfully.")
        
    except Exception as e:
        print(f"Error during comprehensive test: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    test_comprehensive_system()