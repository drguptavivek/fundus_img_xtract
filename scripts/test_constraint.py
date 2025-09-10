#!/usr/bin/env python3
"""
Test script to debug the folder_rel constraint issue.
"""

import sys
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from models import engine

def test_constraint():
    """Test the folder_rel constraint."""
    with engine.connect() as conn:
        # Test the constraint logic directly
        test_values = [
            "2025_09_10_user1",  # This should pass
            "2025_09_10_user1\\test",  # This should fail
            "test\\path",  # This should fail
            "normal_path",  # This should pass
        ]
        
        for value in test_values:
            # Test the constraint logic
            result = conn.execute(text("SELECT instr(:value, :search)"), {"value": value, "search": "\\"}).fetchone()
            print(f"Value: {value!r} -> instr result: {result[0]}")
            
            # Test the actual constraint expression
            result2 = conn.execute(text("SELECT instr(:value, :search) = 0"), {"value": value, "search": "\\"}).fetchone()
            print(f"Value: {value!r} -> constraint passes: {bool(result2[0])}")
            print()

if __name__ == "__main__":
    test_constraint()