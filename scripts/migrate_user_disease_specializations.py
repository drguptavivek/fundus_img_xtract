"""
Migration script to create user_disease_specializations table.
"""

import sys
from pathlib import Path

# Add the project root to the path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from models import engine

def migrate():
    # Create user_disease_specializations table
    with engine.connect() as conn:
        # Check if table already exists
        result = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='user_disease_specializations'"))
        table_exists = result.fetchone()
        
        if not table_exists:
            print("Creating user_disease_specializations table...")
            conn.execute(text("""
                CREATE TABLE user_disease_specializations (
                    user_id INTEGER NOT NULL,
                    disease_id INTEGER NOT NULL,
                    PRIMARY KEY (user_id, disease_id),
                    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
                    FOREIGN KEY (disease_id) REFERENCES diseases (id) ON DELETE CASCADE
                )
            """))
            print("Table created successfully.")
        else:
            print("user_disease_specializations table already exists.")

if __name__ == "__main__":
    migrate()