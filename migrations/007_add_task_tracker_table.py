"""
Migration to add the task_tracker table for tracking when users start working on tasks.
This enables the stuck task cleanup mechanism to identify tasks that have been 
started but not completed within the time limit.
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import Base, TaskTracker, engine

def run_migration():
    """Create the task_tracker table in the database."""
    print("Creating task_tracker table...")
    Base.metadata.create_all(engine, tables=[TaskTracker.__table__])
    print("task_tracker table created successfully!")

if __name__ == "__main__":
    run_migration()