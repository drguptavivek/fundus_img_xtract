#!/usr/bin/env python3
"""Force populate sample features (deletes existing features).

This script is useful when you want to reset sample features to their default state.
It will delete existing features and recreate them from the defined SAMPLE_FEATURES.
"""

import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from scripts.setup_core_entities import populate_sample_features_force

def main():
    """Force populate sample features."""
    print("⚠️  WARNING: This will DELETE existing sample features and recreate them!")
    print("This is useful for resetting to default sample features.")
    print()
    
    response = input("Do you want to continue? (yes/no): ").strip().lower()
    if response not in ['yes', 'y']:
        print("Operation cancelled by user.")
        return
    
    print("Force populating sample features...")
    populate_sample_features_force()
    print("✅ Sample features force-populated successfully!")

if __name__ == "__main__":
    main()