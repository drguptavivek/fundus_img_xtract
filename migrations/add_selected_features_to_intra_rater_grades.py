"""
Migration script to add selected_features_json field to intra_rater_grades table.
This mirrors the field that exists in the grades table for dual grading.
"""

import sqlite3
import sys
from pathlib import Path

def migrate_database(db_path: str):
    """Add selected_features_json column to intra_rater_grades table."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if column already exists
        cursor.execute("PRAGMA table_info(intra_rater_grades)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'selected_features_json' in columns:
            print("selected_features_json column already exists in intra_rater_grades table")
            return
        
        # Add the column
        print("Adding selected_features_json column to intra_rater_grades table...")
        cursor.execute("""
            ALTER TABLE intra_rater_grades 
            ADD COLUMN selected_features_json TEXT NULL
        """)
        
        conn.commit()
        print("Migration completed successfully")
        
    except Exception as e:
        print(f"Migration failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    # Get database path from models.py or use default
    db_path = "image_manager.db"  # Default SQLite path
    
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    
    if not Path(db_path).exists():
        print(f"Database file not found: {db_path}")
        sys.exit(1)
    
    migrate_database(db_path)