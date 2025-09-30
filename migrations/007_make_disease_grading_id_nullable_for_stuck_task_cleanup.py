"""
Migration to update the grades table to allow tracking of tasks that have been started but not yet submitted.
This involves making the disease_grading_id column nullable so we can create placeholder records
when a user begins working on a task.
"""
from models import Base, Grade
from sqlalchemy import Column, Integer, DateTime, String, Text, Float, ForeignKey, CheckConstraint, UniqueConstraint, Index
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from datetime import datetime
from utils.utc_now import utcnow  # assuming this is available in your project

def migrate():
    # This would normally be handled by a proper migration framework
    # For now, this is conceptual code showing the changes needed
    pass

if __name__ == "__main__":
    migrate()