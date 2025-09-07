#!/usr/bin/env python3
"""
Management command to run the matching process for dual grading.
"""

import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from grading.matching import run_matching

if __name__ == "__main__":
    print("Running matching process...")
    try:
        run_matching()
        print("Matching process completed successfully.")
    except Exception as e:
        print(f"Error running matching process: {e}")
        sys.exit(1)