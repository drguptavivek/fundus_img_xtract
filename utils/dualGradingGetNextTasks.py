"""
Utility functions for getting the next eligible dual grading tasks. 
"""

from sqlalchemy.orm import selectinload
from sqlalchemy import and_, or_, func
from models import Session, GradingTask, User, UserDiseaseUnitRole, LabUnit, Grade
from typing import Optional, Union
import random
from datetime import datetime, timedelta

from utils.dualGradingEligibility import _get_user_eligible_lab_unit_ids, _has_user_graded_task_2weeks
from datetime import datetime, timedelta, timezone
from models import Grade


def _has_user_graded_task_6hr(db, user_id: int, task_id: int) -> bool:
    """
    Check if a user has graded a task in the last 6 hours (or configured timeframe).
    This is used for revision functionality to allow arbitrators to revise grades.
    
    Args:
        db: Database session
        user_id: The ID of the user
        task_id: The ID of the task
        
    Returns:
        True if user has graded the task in the last 6 hours, False otherwise
    """
    from datetime import datetime, timedelta, timezone
    import os
    
    # Get the revision timeframe from environment variable (default to 6 hours)
    revision_hours = int(os.getenv("ARBITRATOR_REVISION_HOURS", "6"))
    
    # Calculate the cutoff time
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=revision_hours)
    
    # Get all grades by this user for this task
    user_grades = db.query(Grade).filter(
        Grade.grader_user_id == user_id,
        Grade.task_id == task_id
    ).all()
    
    # Check if any of the grades were created recently
    for grade in user_grades:
        # Handle timezone-naive datetimes from the database
        grade_created_at = grade.created_at
        if grade_created_at.tzinfo is None:
            # Assume naive datetime is in UTC
            grade_created_at = grade_created_at.replace(tzinfo=timezone.utc)
        
        if grade_created_at >= cutoff_time:
            return True
    
    return False


def _get_filtered_tasks(db, user_id: int, disease_id: int, role_slot: str, eligible_lab_unit_ids: list) -> list:
    """
    Get filtered tasks based on role slot and other criteria.
    
    Args:
        db: Database session
        user_id: The ID of the user
        disease_id: The disease ID
        role_slot: The role slot ('resident', 'resident2', or 'arbitrator')
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
    elif role_slot == "resident2":
        # Resident2 graders see tasks where resident has completed grading
        query = query.filter(GradingTask.state == "resident_done")
    
    # Get all matching tasks
    tasks = query.all()
    
    # Filter out tasks that the user has graded in the past 2 weeks
    filtered_tasks = []
    for task in tasks:
        if not _has_user_graded_task_2weeks(db, user_id, task.id):
            filtered_tasks.append(task)
    
    return filtered_tasks


def get_next_eligible_resident_task(user_id: int, disease_id: int, lab_unit_id: Optional[int] = None, db=None) -> Optional[Union[GradingTask, str]]:
    """
    Get the next eligible task for a resident user.
    
    Args:
        user_id: The ID of the user (must be a resident or admin)
        disease_id: The disease ID (required)
        lab_unit_id: Optional lab unit ID to filter by
        db: Optional database session (if not provided, a new session will be created)
        
    Returns:
        The next eligible GradingTask, None if no tasks are available, 
        or a helpful message if no suitable tasks are found after 3 tries
    """
    close_db = False
    if db is None:
        db = Session()
        close_db = True
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
        if close_db:
            db.close()


def get_next_eligible_resident2_task(user_id: int, disease_id: int, lab_unit_id: Optional[int] = None, db=None) -> Optional[Union[GradingTask, str]]:
    """
    Get the next eligible task for a resident2 user.
    
    Args:
        user_id: The ID of the user (must be an ophthalmologist or admin)
        disease_id: The disease ID (required)
        lab_unit_id: Optional lab unit ID to filter by
        db: Optional database session (if not provided, a new session will be created)
        
    Returns:
        The next eligible GradingTask, None if no tasks are available, 
        or a helpful message if no suitable tasks are found after 3 tries
    """
    close_db = False
    if db is None:
        db = Session()
        close_db = True
    try:
        # Get user's eligible lab unit IDs for resident2 role and specified disease
        eligible_lab_unit_ids = _get_user_eligible_lab_unit_ids(db, user_id, disease_id, "resident2")
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
            tasks = _get_filtered_tasks(db, user_id, disease_id, "resident2", eligible_lab_unit_ids)
            
            # If we have tasks, return a random one
            if tasks:
                return random.choice(tasks)
        
        # If we've tried 3 times and still don't have tasks, return a helpful message
        return "No suitable tasks available at this time. All tasks have been recently graded by you or no tasks match your criteria."
        
    finally:
        if close_db:
            db.close()


def get_next_eligible_arbitrator_task(user_id: int, disease_id: int, lab_unit_id: Optional[int] = None, db=None) -> Optional[Union[GradingTask, str]]:
    """
    Get the next eligible task for an arbitrator user.
    
    Args:
        user_id: The ID of the user (must be an ophthalmologist or admin)
        disease_id: The disease ID (required)
        lab_unit_id: Optional lab unit ID to filter by
        db: Optional database session (if not provided, a new session will be created)
        
    Returns:
        The next eligible GradingTask, None if no tasks are available, 
        or a helpful message if no suitable tasks are found after 3 tries
    """
    close_db = False
    if db is None:
        db = Session()
        close_db = True
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
        if close_db:
            db.close()


def _atomically_get_and_lock_task(db, user_id: int, disease_id: int, role_slot: str, eligible_lab_unit_ids: list):
    """
    Atomically get and lock a task for a user to prevent race conditions.
    This function uses SELECT FOR UPDATE to ensure no other user can get the same task.
    
    Args:
        db: Database session
        user_id: The ID of the user
        disease_id: The disease ID
        role_slot: The role slot ('resident', 'resident2', or 'arbitrator')
        eligible_lab_unit_ids: List of lab unit IDs the user is eligible for
    
    Returns:
        The locked GradingTask or None if no eligible tasks are available
    """
    # Build the base query
    query = db.query(GradingTask).filter(
        GradingTask.lab_unit_id.in_(eligible_lab_unit_ids),
        GradingTask.disease_id == disease_id
    )
    
    # Filter by role-specific states
    if role_slot == "arbitrator":
        query = query.filter(GradingTask.state == "arbitration")
    elif role_slot == "resident":
        query = query.filter(GradingTask.state == "pending")
    elif role_slot == "resident2":
        query = query.filter(GradingTask.state == "resident_done")
    
    # Use SELECT FOR UPDATE to lock the rows
    # Order randomly and limit to 1 to get just one task locked
    task = query.with_for_update().order_by(func.random()).first()
    
    # If a task was found, verify that the user hasn't graded it recently
    if task and not _has_user_graded_task_2weeks(db, user_id, task.id):
        return task
    
    return None


def get_next_eligible_resident_task_atomic(user_id: int, disease_id: int, lab_unit_id: Optional[int] = None, db=None) -> Optional[Union[GradingTask, str]]:
    """
    Get the next eligible task for a resident user with atomic locking to prevent race conditions.
    
    Args:
        user_id: The ID of the user (must be a resident or admin)
        disease_id: The disease ID (required)
        lab_unit_id: Optional lab unit ID to filter by
        db: Optional database session (if not provided, a new session will be created)
        
    Returns:
        The next eligible GradingTask, None if no tasks are available, 
        or a helpful message if no suitable tasks are found after 3 tries
    """
    close_db = False
    if db is None:
        db = Session()
        close_db = True
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
        
        # Try up to 3 times to find a suitable task with atomic locking
        for attempt in range(3):
            task = _atomically_get_and_lock_task(db, user_id, disease_id, "resident", eligible_lab_unit_ids)
            if task:
                return task
        
        # If we've tried 3 times and still don't have tasks, return a helpful message
        return "No suitable tasks available at this time. All tasks have been recently graded by you or no tasks match your criteria."
        
    finally:
        if close_db:
            db.close()


def get_next_eligible_resident2_task_atomic(user_id: int, disease_id: int, lab_unit_id: Optional[int] = None, db=None) -> Optional[Union[GradingTask, str]]:
    """
    Get the next eligible task for a resident2 user with atomic locking to prevent race conditions.
    
    Args:
        user_id: The ID of the user (must be an ophthalmologist or admin)
        disease_id: The disease ID (required)
        lab_unit_id: Optional lab unit ID to filter by
        db: Optional database session (if not provided, a new session will be created)
        
    Returns:
        The next eligible GradingTask, None if no tasks are available, 
        or a helpful message if no suitable tasks are found after 3 tries
    """
    close_db = False
    if db is None:
        db = Session()
        close_db = True
    try:
        # Get user's eligible lab unit IDs for resident2 role and specified disease
        eligible_lab_unit_ids = _get_user_eligible_lab_unit_ids(db, user_id, disease_id, "resident2")
        if eligible_lab_unit_ids is None:
            return None
        
        # If a specific lab unit is requested, check if user is eligible for it
        if lab_unit_id:
            if lab_unit_id not in eligible_lab_unit_ids:
                return None
            # Filter to only the specified lab unit
            eligible_lab_unit_ids = [lab_unit_id]
        
        # Try up to 3 times to find a suitable task with atomic locking
        for attempt in range(3):
            task = _atomically_get_and_lock_task(db, user_id, disease_id, "resident2", eligible_lab_unit_ids)
            if task:
                return task
        
        # If we've tried 3 times and still don't have tasks, return a helpful message
        return "No suitable tasks available at this time. All tasks have been recently graded by you or no tasks match your criteria."
        
    finally:
        if close_db:
            db.close()


def get_next_eligible_arbitrator_task_atomic(user_id: int, disease_id: int, lab_unit_id: Optional[int] = None, db=None) -> Optional[Union[GradingTask, str]]:
    """
    Get the next eligible task for an arbitrator user with atomic locking to prevent race conditions.
    
    Args:
        user_id: The ID of the user (must be an ophthalmologist or admin)
        disease_id: The disease ID (required)
        lab_unit_id: Optional lab unit ID to filter by
        db: Optional database session (if not provided, a new session will be created)
        
    Returns:
        The next eligible GradingTask, None if no tasks are available, 
        or a helpful message if no suitable tasks are found after 3 tries
    """
    close_db = False
    if db is None:
        db = Session()
        close_db = True
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
        
        # Try up to 3 times to find a suitable task with atomic locking
        for attempt in range(3):
            task = _atomically_get_and_lock_task(db, user_id, disease_id, "arbitrator", eligible_lab_unit_ids)
            if task:
                return task
        
        # If we've tried 3 times and still don't have tasks, return a helpful message
        return "No suitable tasks available at this time. All tasks have been recently graded by you or no tasks match your criteria."
        
    finally:
        if close_db:
            db.close()
