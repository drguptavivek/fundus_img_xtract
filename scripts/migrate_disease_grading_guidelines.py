"""
Migration script to add guidelines column to disease_gradings table.
"""

import sys
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from models import engine

def migrate(dry_run=False):
    """
    Add guidelines column to disease_gradings table.
    
    Args:
        dry_run (bool): If True, only show what would be done without making changes
    """
    print("Preparing to add guidelines column to disease_gradings table...")
    
    if dry_run:
        print("DRY RUN - No changes will be made")
        print("Would execute: ALTER TABLE disease_gradings ADD COLUMN guidelines TEXT")
    else:
        print("Applying changes...")
        with engine.connect() as conn:
            # Add the guidelines column
            conn.execute(text("ALTER TABLE disease_gradings ADD COLUMN guidelines TEXT"))
            conn.commit()
        print("Guidelines column added to disease_gradings table.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Add guidelines column to disease_gradings table")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without making changes")
    args = parser.parse_args()
    
    migrate(dry_run=args.dry_run)