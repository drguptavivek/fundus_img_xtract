#!/usr/bin/env python3
"""
Test script to verify relative path functionality in DirectImageUpload model
"""
import os
import sys
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from models import DirectImageUpload, BASE_DIR

def test_relative_path_functionality():
    """Test the relative and absolute path functionality"""
    print("Testing DirectImageUpload relative path functionality...")
    
    # Create a mock DirectImageUpload instance with a relative path
    relative_path = "files/direct_uploads/2023_01_01/test_image.jpg"
    upload = DirectImageUpload()
    upload.filepath = relative_path
    
    # Test relative_filepath property
    assert upload.relative_filepath == relative_path
    print("✓ relative_filepath property works correctly")
    
    # Test absolute_filepath property
    expected_absolute_path = str(BASE_DIR / relative_path)
    assert upload.absolute_filepath == expected_absolute_path
    print("✓ absolute_filepath property works correctly")
    
    # Test that the absolute path is correctly formed
    assert os.path.isabs(upload.absolute_filepath)
    print("✓ absolute_filepath returns an absolute path")
    
    print("\nAll tests passed! ✓")

if __name__ == "__main__":
    test_relative_path_functionality()