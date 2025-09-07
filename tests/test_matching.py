#!/usr/bin/env python3
"""
Test script for the dual grading matching and arbitration system.
"""

import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Session, EncounterFile, DirectImageUpload, ImageGrading, User
from grading.matching import run_matching, get_matching_stats


def test_matching_system():
    """Test the matching system."""
    print("Testing matching system...")
    
    # Get initial stats
    stats = get_matching_stats()
    print(f"Initial stats: {stats}")
    
    # Run matching process
    print("Running matching process...")
    run_matching()
    
    # Get stats after matching
    stats = get_matching_stats()
    print(f"Stats after matching: {stats}")
    
    print("Test completed successfully.")


if __name__ == "__main__":
    test_matching_system()