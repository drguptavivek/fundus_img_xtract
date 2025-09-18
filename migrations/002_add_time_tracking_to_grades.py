"""
Migration script to add time tracking fields to the grades table.
This adds start_time and time_taken columns to track grading duration.
"""

from sqlalchemy import Column, Integer, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set up database connection
BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'image_manager.db'}")

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL)

Session = sessionmaker(bind=engine)
session = Session()

def upgrade():
    """Add start_time and time_taken columns to grades table."""
    try:
        # Add start_time column (nullable to accommodate existing records)
        session.execute(text("ALTER TABLE grades ADD COLUMN start_time DATETIME"))
        
        # Add time_taken column (nullable to accommodate existing records)
        session.execute(text("ALTER TABLE grades ADD COLUMN time_taken INTEGER"))
        
        session.commit()
        print("Successfully added time tracking columns to grades table.")
    except Exception as e:
        session.rollback()
        print(f"Error adding columns: {e}")
        raise
    finally:
        session.close()

def downgrade():
    """Remove start_time and time_taken columns from grades table.
    
    Note: SQLite doesn't support dropping columns directly, so this is a no-op
    for SQLite. For other databases, you would implement the column removal.
    """
    print("Downgrade not implemented for SQLite (does not support dropping columns).")
    print("For other databases, implement column removal here.")

if __name__ == "__main__":
    upgrade()