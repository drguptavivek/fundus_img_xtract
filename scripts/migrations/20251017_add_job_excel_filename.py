#!/usr/bin/env python3
"""
Migration script to add excel_filename and upload_type fields to the jobs table.
This will store the original Excel filename and type of upload for all jobs.
"""

import os
import sys
from pathlib import Path

# Add the parent directory to the path so we can import our modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from models import Session, Job, engine
from sqlalchemy import text


def upgrade():
    """Add the excel_filename and upload_type columns to the jobs table."""
    print("Adding excel_filename and upload_type columns to jobs table...")
    
    # Add the columns to the table
    with engine.connect() as conn:
        conn.execute(text("""
            ALTER TABLE jobs
            ADD COLUMN excel_filename VARCHAR(255)
        """))
        conn.execute(text("""
            ALTER TABLE jobs
            ADD COLUMN upload_type VARCHAR(50)
        """))
        conn.commit()
    
    print("✓ excel_filename and upload_type columns added successfully.")


def downgrade():
    """Remove the excel_filename and upload_type columns from the jobs table."""
    print("Removing excel_filename and upload_type columns from jobs table...")
    
    # Remove the columns from the table
    with engine.connect() as conn:
        # SQLite doesn't support DROP COLUMN directly, so we need to recreate the table
        conn.execute(text("""
            CREATE TABLE jobs_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token VARCHAR(255) UNIQUE NOT NULL,
                status VARCHAR(50) DEFAULT 'queued',
                error TEXT,
                rejected_summary TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                uploader_user_id INTEGER,
                uploader_username VARCHAR(150),
                uploader_ip VARCHAR(64),
                lab_unit_id INTEGER,
                FOREIGN KEY (lab_unit_id) REFERENCES lab_units (id)
            )
        """))
        
        # Copy data from old table to new table
        conn.execute(text("""
            INSERT INTO jobs_new (
                id, token, status, error, rejected_summary, created_at, updated_at,
                uploader_user_id, uploader_username, uploader_ip, lab_unit_id
            )
            SELECT
                id, token, status, error, rejected_summary, created_at, updated_at,
                uploader_user_id, uploader_username, uploader_ip, lab_unit_id
            FROM jobs
        """))
        
        # Drop old table and rename new table
        conn.execute(text("DROP TABLE jobs"))
        conn.execute(text("ALTER TABLE jobs_new RENAME TO jobs"))
        
        # Recreate indexes
        conn.execute(text("CREATE INDEX ix_jobs_token ON jobs (token)"))
        conn.execute(text("CREATE INDEX ix_jobs_status ON jobs (status)"))
        conn.execute(text("CREATE INDEX ix_jobs_created_at ON jobs (created_at)"))
        conn.execute(text("CREATE INDEX ix_jobs_uploader_user_id ON jobs (uploader_user_id)"))
        conn.execute(text("CREATE INDEX ix_jobs_uploader_username ON jobs (uploader_username)"))
        conn.execute(text("CREATE INDEX ix_jobs_uploader_ip ON jobs (uploader_ip)"))
        conn.execute(text("CREATE INDEX ix_jobs_lab_unit_id ON jobs (lab_unit_id)"))
        
        conn.commit()
    
    print("✓ excel_filename and upload_type columns removed successfully.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "downgrade":
        downgrade()
    else:
        upgrade()