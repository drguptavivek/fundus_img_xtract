#!/usr/bin/env python3
"""
Test script for the arbitration system.
"""

import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Session, EncounterFile, DirectImageUpload, ImageGrading


def test_arbitration_system():
    """Test the arbitration system."""
    print("Testing arbitration system...")
    
    # Get a session
    db = Session()
    
    try:
        # Test with EncounterFile
        encounter = db.query(EncounterFile).first()
        if encounter:
            print(f"Encounter file UUID: {encounter.uuid}")
            print(f"Initial arbitration status: is_arbitration = {encounter.is_arbitration}")
            
            # Test arbitration
            encounter.is_arbitration = True
            db.add(encounter)
            db.commit()
            
            # Refresh and check
            db.refresh(encounter)
            print(f"Arbitration status after setting: is_arbitration = {encounter.is_arbitration}")
            
            # Test resetting arbitration
            encounter.is_arbitration = False
            db.add(encounter)
            db.commit()
            
            # Refresh and check
            db.refresh(encounter)
            print(f"Arbitration status after resetting: is_arbitration = {encounter.is_arbitration}")
        else:
            print("No encounter files found in database.")
            
        # Test with DirectImageUpload
        direct_upload = db.query(DirectImageUpload).first()
        if direct_upload:
            print(f"Direct upload UUID: {direct_upload.uuid}")
            print(f"Initial arbitration status: is_arbitration = {direct_upload.is_arbitration}")
            
            # Test arbitration
            direct_upload.is_arbitration = True
            db.add(direct_upload)
            db.commit()
            
            # Refresh and check
            db.refresh(direct_upload)
            print(f"Arbitration status after setting: is_arbitration = {direct_upload.is_arbitration}")
            
            # Test resetting arbitration
            direct_upload.is_arbitration = False
            db.add(direct_upload)
            db.commit()
            
            # Refresh and check
            db.refresh(direct_upload)
            print(f"Arbitration status after resetting: is_arbitration = {direct_upload.is_arbitration}")
        else:
            print("No direct uploads found in database.")
            
        print("Arbitration system test completed successfully.")
        
    except Exception as e:
        print(f"Error during arbitration system test: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    test_arbitration_system()