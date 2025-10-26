#!/usr/bin/env python3
"""
Migration script to add uuid column to intra_rater_tasks table.

Usage:
    uv run scripts/add_uuid_column_to_intra_rater_tasks.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Ensure project root is importable when invoked as a module
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from models import engine  # noqa: E402  (import after sys.path manipulation)
from sqlalchemy import text  # noqa: E402

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def add_uuid_column():
    """Add uuid column to intra_rater_tasks table if it doesn't exist."""
    
    # Check if column already exists
    check_sql = text("""
        PRAGMA table_info(intra_rater_tasks)
    """)
    
    with engine.connect() as conn:
        result = conn.execute(check_sql).fetchall()
        columns = [row[1] for row in result]
        
        if 'uuid' in columns:
            logger.info("uuid column already exists in intra_rater_tasks table")
            return
        
        logger.info("Adding uuid column to intra_rater_tasks table")
        
        # Add the column without UNIQUE constraint (SQLite limitation)
        add_sql = text("""
            ALTER TABLE intra_rater_tasks
            ADD COLUMN uuid TEXT
        """)
        
        try:
            conn.execute(add_sql)
            conn.commit()
            logger.info("Successfully added uuid column to intra_rater_tasks table")
            
            # Add index for performance
            index_sql = text("""
                CREATE INDEX ix_intra_rater_tasks_uuid
                ON intra_rater_tasks(uuid)
            """)
            conn.execute(index_sql)
            conn.commit()
            logger.info("Successfully added uuid index to intra_rater_tasks table")
            
        except Exception as e:
            logger.error(f"Error adding uuid column: {e}")
            conn.rollback()
            raise


def main():
    logger.info("Starting migration to add uuid column to intra_rater_tasks")
    
    try:
        add_uuid_column()
        logger.info("Migration completed successfully")
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()