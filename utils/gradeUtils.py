"""
Utility functions for working with grades and tasks.

Note: All functions in this module expect a database session to be passed as a parameter.
The caller is responsible for managing the session lifecycle (opening and closing).
This design allows for better transaction management and session reuse.
"""

from sqlalchemy.orm import selectinload
from models import Grade, GradingTask, Consensus


def fetch_grade_with_related_data(db, grade_id: int):
    """
    Fetch a grade with all related data.
    
    Args:
        db: Database session (caller is responsible for closing)
        grade_id: The ID of the grade to fetch
        
    Returns:
        Grade object with all related data loaded
    """
    return db.query(Grade).options(
        selectinload(Grade.task).selectinload(GradingTask.disease),
        selectinload(Grade.task).selectinload(GradingTask.encounter_file),
        selectinload(Grade.task).selectinload(GradingTask.direct_image),
        selectinload(Grade.task).selectinload(GradingTask.consensus).selectinload(Consensus.decided_by),
        selectinload(Grade.task).selectinload(GradingTask.consensus).selectinload(Consensus.final_label),
        selectinload(Grade.task).selectinload(GradingTask.grades).selectinload(Grade.grader),
        selectinload(Grade.task).selectinload(GradingTask.grades).selectinload(Grade.label),
        selectinload(Grade.label)
    ).filter(Grade.id == grade_id).first()


def fetch_task_with_related_data(db, task_id: int):
    """
    Fetch a grading task with all related data.
    
    Args:
        db: Database session (caller is responsible for closing)
        task_id: The ID of the task to fetch
        
    Returns:
        GradingTask object with all related data loaded
    """
    return db.query(GradingTask).options(
        selectinload(GradingTask.disease),
        selectinload(GradingTask.encounter_file),
        selectinload(GradingTask.direct_image),
        selectinload(GradingTask.consensus).selectinload(Consensus.decided_by),
        selectinload(GradingTask.consensus).selectinload(Consensus.final_label),
        selectinload(GradingTask.grades).selectinload(Grade.grader),
        selectinload(GradingTask.grades).selectinload(Grade.label)
    ).filter(GradingTask.id == task_id).first()


def fetch_existing_grade_for_user(db, task_id: int, user_id: int, slot_type: str):
    """
    Fetch existing grade for this user and slot (for review purposes).
    
    Args:
        db: Database session (caller is responsible for closing)
        task_id: The ID of the task
        user_id: The ID of the user
        slot_type: The slot type (resident, faculty, arbitrator)
        
    Returns:
        Grade object if found, None otherwise
    """
    return db.query(Grade).filter(
        Grade.task_id == task_id,
        Grade.grader_user_id == user_id,
        Grade.role_slot == slot_type
    ).first()