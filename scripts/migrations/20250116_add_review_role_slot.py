"""
Migration script to add 'review' as a valid role_slot in the grades table.

This script updates the check constraint to allow 'review' as a valid role_slot
in addition to 'resident', 'resident2', 'arbitrator', and 'ai'.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from sqlalchemy import text
from models import engine, Session

def migrate():
    """Update the check constraint to allow 'review' as a valid role_slot."""
    print("Starting migration: Add 'review' role_slot to grades table...")
    
    with engine.connect() as conn:
        # Begin transaction
        trans = conn.begin()
        
        try:
            # For SQLite, we need to drop and recreate the table with the new constraint
            if engine.dialect.name == 'sqlite':
                # Get the current table structure
                result = conn.execute(text("SELECT sql FROM sqlite_master WHERE type='table' AND name='grades'"))
                table_sql = result.fetchone()[0]
                print(f"Current table SQL: {table_sql}")
                
                # Create a new table with the updated constraint
                conn.execute(text("""
                    CREATE TABLE grades_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        task_id INTEGER NOT NULL REFERENCES grading_tasks(id) ON DELETE CASCADE,
                        grader_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        role_slot VARCHAR(16) NOT NULL,
                        disease_grading_id INTEGER NOT NULL REFERENCES disease_gradings(id),
                        comment TEXT,
                        time_taken REAL,
                        start_time DATETIME,
                        created_at DATETIME NOT NULL,
                        updated_at DATETIME NOT NULL,
                        disease_name VARCHAR(255),
                        grade_name VARCHAR(64),
                        grade_description TEXT,
                        ai_model_id INTEGER REFERENCES ai_models(id) ON DELETE SET NULL,
                        ai_model_name VARCHAR(255),
                        ai_model_version VARCHAR(64),
                        FOREIGN KEY (task_id) REFERENCES grading_tasks (id) ON DELETE CASCADE,
                        FOREIGN KEY (grader_user_id) REFERENCES users (id) ON DELETE CASCADE,
                        FOREIGN KEY (disease_grading_id) REFERENCES disease_gradings (id),
                        FOREIGN KEY (ai_model_id) REFERENCES ai_models (id) ON DELETE SET NULL,
                        CHECK (role_slot IN ('resident','resident2','arbitrator','ai','review'))
                    )
                """))
                
                # Copy data from the old table to the new table
                conn.execute(text("""
                    INSERT INTO grades_new (
                        id, task_id, grader_user_id, role_slot, disease_grading_id, 
                        comment, time_taken, start_time, created_at, updated_at,
                        disease_name, grade_name, grade_description, ai_model_id,
                        ai_model_name, ai_model_version
                    )
                    SELECT 
                        id, task_id, grader_user_id, role_slot, disease_grading_id,
                        comment, time_taken, start_time, created_at, updated_at,
                        disease_name, grade_name, grade_description, ai_model_id,
                        ai_model_name, ai_model_version
                    FROM grades
                """))
                
                # Drop the old table
                conn.execute(text("DROP TABLE grades"))
                
                # Rename the new table to the original name
                conn.execute(text("ALTER TABLE grades_new RENAME TO grades"))
                
                # Recreate indexes
                conn.execute(text("CREATE INDEX ix_grade_task_slot ON grades (task_id, role_slot)"))
                conn.execute(text("CREATE INDEX ix_grade_user_slot ON grades (grader_user_id, role_slot)"))
                conn.execute(text("CREATE UNIQUE INDEX uq_grade_task_user_slot ON grades (task_id, grader_user_id, role_slot)"))
                
            else:
                # For other databases like PostgreSQL, we can just update the constraint
                conn.execute(text("""
                    ALTER TABLE grades 
                    DROP CONSTRAINT ck_grade_role_slot_valid
                """))
                
                conn.execute(text("""
                    ALTER TABLE grades 
                    ADD CONSTRAINT ck_grade_role_slot_valid 
                    CHECK (role_slot IN ('resident','resident2','arbitrator','ai','review'))
                """))
            
            # Commit the transaction
            trans.commit()
            print("Migration completed successfully!")
            
        except Exception as e:
            # Roll back in case of error
            trans.rollback()
            print(f"Migration failed: {e}")
            raise

if __name__ == "__main__":
    migrate()