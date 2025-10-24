#!/usr/bin/env python3
"""Remove features_json column from disease_gradings table after migration to GradingsFeatures."""
from __future__ import annotations

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from sqlalchemy import text
from models import engine
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DISEASE_GRADINGS_TABLE = "disease_gradings"
FEATURES_JSON_COLUMN = "features_json"

def column_exists(table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table."""
    with engine.connect() as conn:
        result = conn.execute(text(f"PRAGMA table_info({table_name})"))
        columns = [row[1] for row in result.fetchall() if row[1].lower() == column_name.lower()]
        return column_name.lower() in columns

def main():
    """Main migration function."""
    logger.info("Starting migration: Remove features_json column from disease_gradings table...")
    
    try:
        # Check if column exists
        if not column_exists(DISEASE_GRADINGS_TABLE, FEATURES_JSON_COLUMN):
            logger.info(f"Column {FEATURES_JSON_COLUMN} does not exist in table {DISEASE_GRADINGS_TABLE}. Skipping migration.")
            logger.info("Migration completed successfully.")
            return
        
        # Drop the features_json column
        with engine.connect() as conn:
            conn.execute(text(f"ALTER TABLE {DISEASE_GRADINGS_TABLE} DROP COLUMN {FEATURES_JSON_COLUMN}"))
            conn.commit()
            
        logger.info(f"Successfully removed {FEATURES_JSON_COLUMN} column from {DISEASE_GRADINGS_TABLE} table.")
        logger.info("Migration completed successfully.")
        
    except Exception as e:
        logger.error(f"Migration failed: {str(e)}")
        raise

if __name__ == "__main__":
    main()