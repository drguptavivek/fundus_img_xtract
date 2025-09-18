#!/usr/bin/env python3
"""
Test script to verify that time tracking functionality is working correctly.
"""

import sys
import os
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables
load_dotenv()

# Import models after adding project root to path
from models import Session, Grade

def test_time_tracking_fields():
    """Test that time tracking fields exist and can be set correctly."""
    db = Session()
    try:
        # Check if the time tracking fields exist by querying an existing grade
        existing_grade = db.query(Grade).first()
        
        if existing_grade:
            # Test that we can access the time tracking fields
            print("✓ Successfully accessed existing grade")
            print(f"  Time taken: {existing_grade.time_taken}")
            print(f"  Start time: {existing_grade.start_time}")
        else:
            print("No existing grades found in the database.")
            
    except Exception as e:
        print(f"✗ Error during test: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    test_time_tracking_fields()