"""Test database setup for isolated testing."""

import os
import sys
from pathlib import Path
import tempfile

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from models import Base, engine
from sqlalchemy import create_engine


def setup_test_database():
    """Setup a fresh test database."""
    # Create test database path
    test_db_path = project_root / 'tests' / 'test_zip_processing.db'
    
    # Remove existing test database if it exists
    if test_db_path.exists():
        test_db_path.unlink()
    
    # Create new test database
    test_engine = create_engine(f'sqlite:///{test_db_path}')
    
    # Create all tables
    Base.metadata.create_all(test_engine)
    
    print(f"Test database created at: {test_db_path}")
    return test_engine


if __name__ == "__main__":
    setup_test_database()