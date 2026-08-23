"""
Utility functions for working with grades and tasks.

Note: All functions in this module expect a database session to be passed as a parameter.
The caller is responsible for managing the session lifecycle (opening and closing).
This design allows for better transaction management and session reuse.
"""

from typing import List, Tuple, Optional, Dict, Any, Iterable, Union
from datetime import date
from sqlalchemy import desc
from sqlalchemy.orm import selectinload
from models import (
    Grade,
    GradingTask,
    Consensus,
    Disease,
    DiseaseGrading,
    LabUnit,
    Hospital,
    User,
    UserDiseaseUnitRole,
    EncounterFile,
    DirectImageUpload,
    EncounterSetGradingPackage,
    EncounterSetImage,
)

def fetch_task_with_related_data(db, task_id: int, user: Optional[User] = None):
    """
    Fetch a grading task with all related data.
    
    Args:
        db: Database session (caller is responsible for closing)
        task_id: The ID of the task to fetch
        user: Optional user for scoping
        
    Returns:
        GradingTask object with all related data loaded
    """
    q = db.query(GradingTask).options(
        selectinload(GradingTask.disease),
        selectinload(GradingTask.encounter_file),
        selectinload(GradingTask.direct_image),
        selectinload(GradingTask.encounter_set_image),
        selectinload(GradingTask.encounter_set_package),
        selectinload(GradingTask.consensus).selectinload(Consensus.decided_by),
        selectinload(GradingTask.consensus).selectinload(Consensus.final_label),
        selectinload(GradingTask.grades).selectinload(Grade.grader),
        selectinload(GradingTask.grades).selectinload(Grade.label)
    ).filter(GradingTask.id == task_id)
    
    return q.first()


def fetch_existing_grade_for_user(db, task_id: int, user_id: int, slot_type: str, user: Optional[User] = None):
    """
    Fetch existing grade for this user and slot (for review purposes).
    
    Args:
        db: Database session (caller is responsible for closing)
        task_id: The ID of the task
        user_id: The ID of the user
        slot_type: The slot type (resident, resident2, arbitrator)
        user: Optional user for scoping
        
    Returns:
        Grade object if found, None otherwise
    """
    q = db.query(Grade).filter(
        Grade.task_id == task_id,
        Grade.grader_user_id == user_id,
        Grade.role_slot == slot_type
    )
    
    return q.first()


