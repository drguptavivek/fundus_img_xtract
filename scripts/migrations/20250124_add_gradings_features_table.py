#!/usr/bin/env python3
"""Add gradings_features table to replace features_json field."""
from __future__ import annotations

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from sqlalchemy import text, inspect
from models import engine, Base
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

GRADINGS_FEATURES_TABLE = "gradings_features"

def table_exists(table_name: str) -> bool:
    """Check if a table exists in the database."""
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()

def create_gradings_features_table():
    """Create the gradings_features table."""
    logger.info(f"Creating {GRADINGS_FEATURES_TABLE} table...")
    
    # Create the table using SQLAlchemy metadata
    from models import GradingsFeatures
    GradingsFeatures.__table__.create(engine, checkfirst=True)
    
    logger.info(f"Successfully created {GRADINGS_FEATURES_TABLE} table.")

def main():
    """Main migration function."""
    logger.info("Starting migration: Add gradings_features table...")
    
    try:
        # Check if table already exists
        if table_exists(GRADINGS_FEATURES_TABLE):
            logger.info(f"Table {GRADINGS_FEATURES_TABLE} already exists. Skipping creation.")
        else:
            create_gradings_features_table()
            logger.info(f"Table {GRADINGS_FEATURES_TABLE} created successfully.")
        
        logger.info("Migration completed successfully.")
        
    except Exception as e:
        logger.error(f"Migration failed: {str(e)}")
        raise

if __name__ == "__main__":
    main()