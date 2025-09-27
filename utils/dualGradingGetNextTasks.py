"""
Utility functions for getting the next eligible dual grading tasks.
"""

from sqlalchemy.orm import selectinload
from sqlalchemy import and_, or_
from models import Session, GradingTask, User, UserDiseaseUnitRole, LabUnit, Grade
from typing import Optional, Union
import random
from datetime import datetime, timedelta


def _has_user_graded_task_recently(db, user_id: int, task_id: int) -> bool:
    """
    Check if a user has graded a task in the past 2 weeks.
    
    Args:
        db: Database session
        user_id: The ID of the user
        task_id: The ID of the task
        
    Returns:
        True if user has graded the task in the past 2 weeks, False otherwise
    """
    from datetime import timezone
    # Use timezone-aware datetime for comparison
    two_weeks_ago = datetime.now(timezone.utc) - timedelta(weeks=2)
    
    # Get all grades by this user for this task
    user_grades = db.query(Grade).filter(
        Grade.grader_user_id == user_id,
        Grade.task_id == task_id
    ).all()
    
    # Check if any of the grades were created in the last 2 weeks
    for grade in user_grades:
        # Handle timezone-naive datetimes from the database
        grade_created_at = grade.created_at
        if grade_created_at.tzinfo is None:
            # Assume naive datetime is in UTC
            grade_created_at = grade_created_at.replace(tzinfo=timezone.utc)
        
        if grade_created_at >= two_weeks_ago:
            return True
    
    return False


def _get_user_eligible_lab_unit_ids(db, user_id: int, disease_id: int, role_slot: str) -> Optional[list]:
    """
    Get the list of lab unit IDs that a user is eligible for a specific role and disease.
    
    Args:
        db: Database session
        user_id: The ID of the user
        disease_id: The disease ID
        role_slot: The role slot ('resident', 'faculty', or 'arbitrator')
        
    Returns:
        List of eligible lab unit IDs or None if user has no eligibility
    """
    # Load user with roles
    user = db.query(User).options(selectinload(User.roles)).filter(User.id == user_id).first()
    if not user:
        return None
    
    # Check if user is admin (admins have access to all lab units)
    if user.has_role('admin'):
        lab_units = db.query(LabUnit).all()
        return [lab_unit.id for lab_unit in lab_units]
    
    # Check role-specific permissions
    if role_slot == "resident" and not user.has_role('resident'):
        return None
    elif role_slot in ["faculty", "arbitrator"] and not user.has_role('ophthalmologist'):
        return None
    
    # Build eligibility query based on role slot
    eligibility_query = db.query(UserDiseaseUnitRole).filter(
        UserDiseaseUnitRole.user_id == user_id,
        UserDiseaseUnitRole.disease_id == disease_id,
        UserDiseaseUnitRole.active == True
    )
    
    # Add role-specific filter
    if role_slot == "resident":
        eligibility_query = eligibility_query.filter(UserDiseaseUnitRole.can_grade_resident == True)
    elif role_slot == "faculty":
        eligibility_query = eligibility_query.filter(UserDiseaseUnitRole.can_grade_faculty == True)
    elif role_slot == "arbitrator":
        eligibility_query = eligibility_query.filter(UserDiseaseUnitRole.can_arbitrate == True)
    
    # Get eligible roles
    eligible_roles = eligibility_query.all()
    if not eligible_roles:
        return None
    
    return [role.lab_unit_id for role in eligible_roles]


def _get_filtered_tasks(db, user_id: int, disease_id: int, role_slot: str, eligible_lab_unit_ids: list) -> list:
    """
    Get filtered tasks based on role slot and other criteria.
    
    Args:
        db: Database session
        user_id: The ID of the user
        disease_id: The disease ID
        role_slot: The role slot ('resident', 'faculty', or 'arbitrator')
        eligible_lab_unit_ids: List of lab unit IDs the user is eligible for
        
    Returns:
        List of filtered tasks
    """
    # Build query for tasks
    query = db.query(GradingTask)
    
    # Filter by eligible lab units
    query = query.filter(GradingTask.lab_unit_id.in_(eligible_lab_unit_ids))
        
    # Filter by disease
    query = query.filter(GradingTask.disease_id == disease_id)
        
    # Filter by role-specific states
    if role_slot == "arbitrator":
        # Arbitrators only see arbitration tasks
        query = query.filter(GradingTask.state == "arbitration")
    elif role_slot == "resident":
        # Residents see pending tasks
        query = query.filter(GradingTask.state == "pending")
    elif role_slot == "faculty":
        # Faculty see tasks where resident has completed grading
        query = query.filter(GradingTask.state == "resident_done")
    
    # Get all matching tasks
    tasks = query.all()
    
    # Filter out tasks that the user has graded in the past 2 weeks
    filtered_tasks = []
    for task in tasks:
        if not _has_user_graded_task_recently(db, user_id, task.id):
            filtered_tasks.append(task)
    
    return filtered_tasks


def get_next_eligible_resident_task(user_id: int, disease_id: int, lab_unit_id: Optional[int] = None) -> Optional[Union[GradingTask, str]]:
    """
    Get the next eligible task for a resident user.
    
    Args:
        user_id: The ID of the user (must be a resident or admin)
        disease_id: The disease ID (required)
        lab_unit_id: Optional lab unit ID to filter by
        
    Returns:
        The next eligible GradingTask, None if no tasks are available, 
        or a helpful message if no suitable tasks are found after 3 tries
    """
    db = Session()
    try:
        # Get user's eligible lab unit IDs for resident role and specified disease
        eligible_lab_unit_ids = _get_user_eligible_lab_unit_ids(db, user_id, disease_id, "resident")
        if eligible_lab_unit_ids is None:
            return None
        
        # If a specific lab unit is requested, check if user is eligible for it
        if lab_unit_id:
            if lab_unit_id not in eligible_lab_unit_ids:
                return None
            # Filter to only the specified lab unit
            eligible_lab_unit_ids = [lab_unit_id]
        
        # Try up to 3 times to find a suitable task
        for attempt in range(3):
            # Get filtered tasks
            tasks = _get_filtered_tasks(db, user_id, disease_id, "resident", eligible_lab_unit_ids)
            
            # If we have tasks, return a random one
            if tasks:
                return random.choice(tasks)
        
        # If we've tried 3 times and still don't have tasks, return a helpful message
        return "No suitable tasks available at this time. All tasks have been recently graded by you or no tasks match your criteria."
        
    finally:
        db.close()


def get_next_eligible_faculty_task(user_id: int, disease_id: int, lab_unit_id: Optional[int] = None) -> Optional[Union[GradingTask, str]]:
    """
    Get the next eligible task for a faculty user.
    
    Args:
        user_id: The ID of the user (must be an ophthalmologist or admin)
        disease_id: The disease ID (required)
        lab_unit_id: Optional lab unit ID to filter by
        
    Returns:
        The next eligible GradingTask, None if no tasks are available, 
        or a helpful message if no suitable tasks are found after 3 tries
    """
    db = Session()
    try:
        # Get user's eligible lab unit IDs for faculty role and specified disease
        eligible_lab_unit_ids = _get_user_eligible_lab_unit_ids(db, user_id, disease_id, "faculty")
        if eligible_lab_unit_ids is None:
            return None
        
        # If a specific lab unit is requested, check if user is eligible for it
        if lab_unit_id:
            if lab_unit_id not in eligible_lab_unit_ids:
                return None
            # Filter to only the specified lab unit
            eligible_lab_unit_ids = [lab_unit_id]
        
        # Try up to 3 times to find a suitable task
        for attempt in range(3):
            # Get filtered tasks
            tasks = _get_filtered_tasks(db, user_id, disease_id, "faculty", eligible_lab_unit_ids)
            
            # If we have tasks, return a random one
            if tasks:
                return random.choice(tasks)
        
        # If we've tried 3 times and still don't have tasks, return a helpful message
        return "No suitable tasks available at this time. All tasks have been recently graded by you or no tasks match your criteria."
        
    finally:
        db.close()


def get_next_eligible_arbitrator_task(user_id: int, disease_id: int, lab_unit_id: Optional[int] = None) -> Optional[Union[GradingTask, str]]:
    """
    Get the next eligible task for an arbitrator user.
    
    Args:
        user_id: The ID of the user (must be an ophthalmologist or admin)
        disease_id: The disease ID (required)
        lab_unit_id: Optional lab unit ID to filter by
        
    Returns:
        The next eligible GradingTask, None if no tasks are available, 
        or a helpful message if no suitable tasks are found after 3 tries
    """
    db = Session()
    try:
        # Get user's eligible lab unit IDs for arbitrator role and specified disease
        eligible_lab_unit_ids = _get_user_eligible_lab_unit_ids(db, user_id, disease_id, "arbitrator")
        if eligible_lab_unit_ids is None:
            return None
        
        # If a specific lab unit is requested, check if user is eligible for it
        if lab_unit_id:
            if lab_unit_id not in eligible_lab_unit_ids:
                return None
            # Filter to only the specified lab unit
            eligible_lab_unit_ids = [lab_unit_id]
        
        # Try up to 3 times to find a suitable task
        for attempt in range(3):
            # Get filtered tasks
            tasks = _get_filtered_tasks(db, user_id, disease_id, "arbitrator", eligible_lab_unit_ids)
            
            # If we have tasks, return a random one
            if tasks:
                return random.choice(tasks)
        
        # If we've tried 3 times and still don't have tasks, return a helpful message
        return "No suitable tasks available at this time. All tasks have been recently graded by you or no tasks match your criteria."
        
    finally:
        db.close()