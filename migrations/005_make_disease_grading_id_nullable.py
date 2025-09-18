"""
Migration script to make the disease_grading_id column in the grades table nullable.
This allows us to create Grade records to track start time before a user submits their grade.
"""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
from pathlib import Path
import os

# Load environment variables
load_dotenv()

# Set up database connection
BASE_DIR = Path(__file__).resolve().parent
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'image_manager.db'}")

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL)

Session = sessionmaker(bind=engine)
session = Session()

def upgrade():
    """Modify disease_grading_id column to be nullable."""
    try:
        if DATABASE_URL.startswith("sqlite"):
            # SQLite doesn't support modifying columns directly
            # We need to do this in steps:
            # 1. Create a new table with the correct schema
            # 2. Copy data from the old table to the new table
            # 3. Drop the old table
            # 4. Rename the new table to the original name
            
            print("SQLite database detected. Performing table rebuild...")
            
            # Step 1: Create new table with correct schema
            session.execute(text("""
                CREATE TABLE grades_new (
                    id INTEGER NOT NULL PRIMARY KEY,
                    task_id INTEGER NOT NULL,
                    grader_user_id INTEGER NOT NULL,
                    role_slot VARCHAR(16) NOT NULL,
                    disease_grading_id INTEGER,
                    comment TEXT,
                    time_taken INTEGER,
                    start_time DATETIME,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES grading_tasks (id) ON DELETE CASCADE,
                    FOREIGN KEY(grader_user_id) REFERENCES users (id) ON DELETE CASCADE,
                    FOREIGN KEY(disease_grading_id) REFERENCES disease_gradings (id),
                    CHECK (role_slot IN ('resident', 'faculty', 'arbitrator'))
                )
            """))
            
            # Create indexes
            session.execute(text("CREATE INDEX ix_grades_new_task_id ON grades_new (task_id)"))
            session.execute(text("CREATE INDEX ix_grades_new_grader_user_id ON grades_new (grader_user_id)"))
            session.execute(text("CREATE INDEX ix_grades_new_role_slot ON grades_new (role_slot)"))
            session.execute(text("CREATE INDEX ix_grades_new_disease_grading_id ON grades_new (disease_grading_id)"))
            session.execute(text("CREATE INDEX ix_grades_new_task_slot ON grades_new (task_id, role_slot)"))
            session.execute(text("CREATE INDEX ix_grades_new_user_slot ON grades_new (grader_user_id, role_slot)"))
            
            # Step 2: Copy data from old table to new table
            session.execute(text("""
                INSERT INTO grades_new (
                    id, task_id, grader_user_id, role_slot, disease_grading_id, 
                    comment, time_taken, start_time, created_at, updated_at
                )
                SELECT 
                    id, task_id, grader_user_id, role_slot, disease_grading_id, 
                    comment, time_taken, start_time, created_at, updated_at
                FROM grades
            """))
            
            # Step 3: Drop old table
            session.execute(text("DROP TABLE grades"))
            
            # Step 4: Rename new table
            session.execute(text("ALTER TABLE grades_new RENAME TO grades"))
            
            # Recreate the unique constraint
            session.execute(text("""
                CREATE UNIQUE INDEX uq_grade_task_user_slot ON grades (task_id, grader_user_id, role_slot)
            """))
        else:
            # For other databases (PostgreSQL, MySQL, etc.), we can modify the column directly
            session.execute(text("ALTER TABLE grades ALTER COLUMN disease_grading_id DROP NOT NULL"))
        
        session.commit()
        print("Successfully modified disease_grading_id column to be nullable.")
    except Exception as e:
        session.rollback()
        print(f"Error modifying column: {e}")
        raise
    finally:
        session.close()

def downgrade():
    """Revert disease_grading_id column to NOT NULL.
    
    Note: This is a complex operation for SQLite and might not be perfectly reversible.
    For other databases, you would implement: ALTER TABLE grades ALTER COLUMN disease_grading_id SET NOT NULL
    """
    print("Downgrade not implemented. For SQLite, this would require another table rebuild.")

if __name__ == "__main__":
    upgrade()