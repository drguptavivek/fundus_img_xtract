#!/usr/bin/env python3
"""
Migration script to create the disease_gradings table.
"""

import sys
from pathlib import Path

# Add the project root to the path
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models import Base, engine

def migrate(dry_run: bool = False) -> None:
    """Create the disease_gradings table."""
    if dry_run:
        print("[DRY RUN] Would create disease_gradings table...")
        return
    
    print("Creating disease_gradings table...")
    # Create only the disease_gradings table (or any missing tables)
    Base.metadata.create_all(engine, tables=[Base.metadata.tables['disease_gradings']])
    print("disease_gradings table created successfully.")

def main():
    migrate()

if __name__ == "__main__":
    main()