#!/usr/bin/env python3
"""Test script to verify the search functionality fix in imageSearchUtil.py"""

import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.imageSearchUtil import search_images
from db_transaction_manager import get_db_session
from models import DirectImageUpload, EncounterFile


def test_search_functionality():
    """Test the search functionality to ensure the sorting fix works"""
    print("Testing search functionality after sorting fix...")
    
    try:
        # Use the get_db_session context manager to get a session
        with get_db_session() as db_session:
            # Test basic search without filters
            print("Running basic search...")
            images, total_count = search_images(db_session)
            print(f"✓ Basic search successful: {len(images)} images returned, total count: {total_count}")
            
            # Test search with pagination
            print("Running search with pagination...")
            images, total_count = search_images(db_session, page=1, per_page=10)
            print(f"✓ Paginated search successful: {len(images)} images returned, total count: {total_count}")
            
            # Test search with a simple filter
            print("Running search with lab unit filter...")
            # Get some lab unit IDs if they exist
            lab_units_result = db_session.execute(
                "SELECT id FROM lab_units LIMIT 3"
            ).fetchall()
            lab_unit_ids = [row[0] for row in lab_units_result] if lab_units_result else None
            
            if lab_unit_ids:
                images, total_count = search_images(db_session, lab_unit_ids=lab_unit_ids)
                print(f"✓ Filtered search successful: {len(images)} images returned, total count: {total_count}")
            else:
                print("No lab units found, skipping lab unit filter test")
            
            print("✓ All search functionality tests passed!")
            return True
            
    except AttributeError as e:
        if "created_at" in str(e):
            print(f"✗ The sorting error still exists: {e}")
            return False
        else:
            print(f"✗ Unexpected AttributeError: {e}")
            return False
    except Exception as e:
        print(f"✗ Error during search functionality test: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_search_functionality()
    if success:
        print("\n🎉 Search functionality fix verified successfully!")
    else:
        print("\n❌ Search functionality test failed!")
        sys.exit(1)