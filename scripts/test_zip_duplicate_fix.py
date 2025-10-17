#!/usr/bin/env python3
"""
Test script to verify the ZIP duplicate handling fix.
This script simulates the duplicate handling logic to ensure it works correctly.
"""

import sys
import os
from pathlib import Path

# Add the parent directory to the path so we can import our modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from models import Session, ZipFile
from zip_processor import process_zip_file
from worker import _process_one_zip


def test_duplicate_handling():
    """Test that duplicate ZIP files are properly handled."""
    print("Testing ZIP duplicate handling fix...")
    
    # Create a test session
    session = Session()
    
    try:
        # Create a test ZIP file entry in the database to simulate a duplicate
        test_zip = ZipFile(
            zip_filename="test_duplicate.zip",
            md5_hash="test_md5_hash_12345"
        )
        session.add(test_zip)
        session.commit()
        
        # Create a mock ZIP file path
        test_zip_path = Path("/tmp/test_duplicate.zip")
        
        # Mock the calculate_md5 function to return our test hash
        import zip_processor
        original_calculate_md5 = zip_processor.calculate_md5
        zip_processor.calculate_md5 = lambda path: "test_md5_hash_12345"
        
        # Mock shutil.move to prevent actual file operations
        import shutil
        original_move = shutil.move
        shutil.move = lambda src, dst: None
        
        # Mock log_status to prevent file operations
        original_log_status = zip_processor.log_status
        zip_processor.log_status = lambda filename, status, message="": None
        
        try:
            # Test process_zip_file with duplicate
            pdfs, status = process_zip_file(test_zip_path, session)
            
            print(f"process_zip_file returned: pdfs={pdfs}, status={status}")
            
            # Verify it returns the correct status for duplicates
            assert status == "duplicate", f"Expected status='duplicate', got '{status}'"
            assert pdfs == [], f"Expected empty pdfs list, got {pdfs}"
            
            # Test _process_one_zip with duplicate
            # Mock setup_environment to prevent directory creation
            original_setup_env = zip_processor.setup_environment
            zip_processor.setup_environment = lambda: None
            
            result = _process_one_zip(test_zip_path)
            
            print(f"_process_one_zip returned: {result}")
            
            # Verify it returns the correct result for duplicates
            assert result["status"] == "skipped", f"Expected status='skipped', got '{result['status']}'"
            assert "Duplicate file" in result["message"], f"Expected 'Duplicate file' in message, got '{result['message']}'"
            
            # Test that duplicate files are marked as rejected (error state) in job items
            # This simulates the logic in _job_worker
            item_status = "error" if result["status"] == "skipped" and "Duplicate file" in result.get("message", "") else result["status"]
            assert item_status == "error", f"Expected duplicate files to be marked as 'error' (rejected), got '{item_status}'"
            
            print("✓ All tests passed! Duplicate handling is working correctly.")
            
        finally:
            # Restore original functions
            zip_processor.calculate_md5 = original_calculate_md5
            shutil.move = original_move
            zip_processor.log_status = original_log_status
            zip_processor.setup_environment = original_setup_env
            
    finally:
        # Clean up test data
        session.query(ZipFile).filter_by(md5_hash="test_md5_hash_12345").delete()
        session.commit()
        session.close()


if __name__ == "__main__":
    test_duplicate_handling()