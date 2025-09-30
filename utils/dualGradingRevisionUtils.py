"""
Utility functions for dual grading system, specifically for revision eligibility checks.
"""
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from typing import Optional

from models import Grade, GradingTask
from utils.dualGradingFetchDetailUtils import fetch_existing_grade_for_user


def is_user_eligible_for_revision(db: Session, user_id: int, task_id: int, slot_type: str, grade: Grade = None) -> dict:
    """
    Check if a user is eligible to revise their grade for a specific task and slot.
    
    Args:
        db: Database session
        user_id: ID of the user requesting revision
        task_id: ID of the grading task
        slot_type: The slot type ('resident', 'faculty', 'arbitrator')
        grade: The grade object to check (optional, will be fetched if not provided)
        
    Returns:
        A dictionary with the following keys:
        - eligible: boolean indicating if the user is eligible for revision
        - message: string explaining why the user is or isn't eligible
        - is_recent: boolean indicating if the grade was submitted recently enough for revision
    """
    # Default return value
    result = {
        "eligible": False,
        "message": "",
        "is_recent": False
    }
    
    # Check if slot type is valid
    if slot_type not in ['resident', 'faculty', 'arbitrator']:
        result["message"] = f"Invalid slot type: {slot_type}"
        return result

    # Get the grade if not provided
    if grade is None:
        grade = fetch_existing_grade_for_user(db, task_id, user_id, slot_type)
    
    # Check if grade exists
    if not grade:
        result["message"] = f"No existing grade found for user {user_id} in slot {slot_type} for task {task_id}"
        return result
    
    # Check if the grade belongs to the current user
    if grade.grader_user_id != user_id:
        result["message"] = "You are not authorized to revise this grade."
        return result
    
    # For resident and faculty, revision is allowed if the task is not yet finalized
    if slot_type in ['resident', 'faculty']:
        # These users can revise their grades at any point before finalization
        result["eligible"] = True
        result["message"] = "Eligible for revision"
        return result
    
    # For arbitrator, revision is only allowed within 6 hours of submission
    if slot_type == 'arbitrator':
        # Check if grade was submitted within the last 6 hours
        six_hours_ago = datetime.now(timezone.utc) - timedelta(hours=6)
        
        # Make sure we handle timezone-naive datetime properly
        created_at = grade.created_at
        if created_at.tzinfo is None:
            # Model datetimes are likely stored as timezone-naive in UTC
            created_at = created_at.replace(tzinfo=timezone.utc)
        
        is_recent = created_at >= six_hours_ago
        result["is_recent"] = is_recent
        
        if is_recent:
            result["eligible"] = True
            result["message"] = "Eligible for revision (submitted within 6 hours)"
        else:
            result["message"] = "Cannot revise arbitrator grade after 6 hours have passed."
    
    return result


def is_arbitrator_eligible_for_revision(db: Session, user_id: int, task_id: int, task: Optional[GradingTask] = None) -> dict:
    """
    Specific check for arbitrator revision eligibility.
    
    Args:
        db: Database session
        user_id: ID of the user requesting revision
        task_id: ID of the grading task
        task: The GradingTask object (optional, will be fetched if not provided)
        
    Returns:
        A dictionary with eligibility information
    """
    # Get the task if not provided
    if task is None:
        from utils.dualGradingFetchDetailUtils import fetch_task_with_related_data
        task = fetch_task_with_related_data(db, task_id)
        if not task:
            return {
                "eligible": False,
                "message": "Task not found.",
                "grade": None
            }
    
    # Check if user has made an arbitrator grade for this task
    arbitrator_grade = fetch_existing_grade_for_user(db, task_id, user_id, 'arbitrator')
    
    if not arbitrator_grade:
        return {
            "eligible": False,
            "message": "Arbitrator slot is not available for this task.",
            "grade": None
        }
    
    # Check if the grade was made recently (within 6 hours)
    eligibility_result = is_user_eligible_for_revision(db, user_id, task_id, 'arbitrator', arbitrator_grade)
    
    # Add the grade to the result for further use
    eligibility_result["grade"] = arbitrator_grade
    
    return eligibility_result


def check_arbitrator_revision_eligibility(db: Session, user_id: int, task: GradingTask) -> tuple[bool, str]:
    """
    Check if an arbitrator is eligible to revise a grade based on the task state and other conditions.
    This function replicates the logic used in the dual_grading_task function.
    
    Args:
        db: Database session
        user_id: ID of the user requesting revision
        task: The GradingTask object
    
    Returns:
        A tuple of (is_eligible: bool, message: str)
    """
    if task.state == 'final':
        # Check if this user is the arbitrator who made the decision and if it was recent
        arbitrator_grade = next((g for g in task.grades if g.role_slot == 'arbitrator' and g.grader_user_id == user_id), None)
        if arbitrator_grade:
            six_hours_ago = datetime.now(timezone.utc) - timedelta(hours=6)
            created_at = arbitrator_grade.created_at
            if created_at and created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            
            if created_at and created_at >= six_hours_ago:
                # Allow arbitrator to revise their recent decision
                return True, "Eligible for revision (submitted within 6 hours)"
            else:
                return False, "Cannot revise arbitrator grade after 6 hours have passed."
        else:
            return False, "Arbitrator slot is not available for this task."
    
    # For non-final tasks, check if state matches the slot type requirements
    # This is a more generic check
    if task.state == 'arbitration':
        return True, "Eligible for revision (task in arbitration state)"
    else:
        return False, f"Arbitrator slot is not available for this task (task state: {task.state})."


def is_arbitrator_revision_allowed(db: Session, user_id: int, task_id: int, slot: str) -> dict:
    """
    Check if an arbitrator is allowed to revise their grade.
    This function replicates the logic used in dual_grading_submit function to determine if revision is allowed.
    
    Args:
        db: Database session
        user_id: ID of the user requesting revision
        task_id: ID of the grading task
        slot: The slot type ('arbitrator')
    
    Returns:
        A dictionary with the following keys:
        - allowed: boolean indicating if revision is allowed
        - message: string explaining why or why not
        - is_recent: boolean indicating if the existing grade was submitted recently enough for revision
    """
    result = {
        "allowed": False,
        "message": "",
        "is_recent": False
    }
    
    if slot != "arbitrator":
        result["message"] = "This function is only for arbitrator revisions."
        return result

    # We need to fetch the existing grade to verify if it was created within 6 hours
    existing_grade_for_check = fetch_existing_grade_for_user(db, task_id, user_id, slot)
    
    if existing_grade_for_check:
        # Use timezone-aware datetime consistently
        six_hours_ago = datetime.now(timezone.utc) - timedelta(hours=6)
        
        # Make the grade's created_at timezone-aware if it's naive for proper comparison
        created_at = existing_grade_for_check.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        
        is_recent = created_at >= six_hours_ago
        result["is_recent"] = is_recent
        
        if is_recent:
            result["allowed"] = True
            result["message"] = "Arbitrator revision allowed (submitted within 6 hours)"
        else:
            result["message"] = "Arbitrator revision not allowed after 6 hours have passed."
    else:
        # If there's no existing grade for this arbitrator, it's not a revision
        result["message"] = "No existing grade found for this arbitrator - this is not a revision."
    
    return result


def check_revision_eligibility_by_task_state(task_state: str, role_slot: str, grade_created_at: Optional[datetime] = None) -> tuple[bool, str]:
    """
    Check if a user is eligible to revise a grade based on the task state and other conditions.
    
    Args:
        task_state: Current state of the task
        role_slot: Role slot ('resident', 'faculty', 'arbitrator')
        grade_created_at: When the grade was created (needed for arbitrator revisions)
    
    Returns:
        A tuple of (is_eligible: bool, message: str)
    """
    # If task is finalized, only arbitrators can make revisions under specific conditions
    if task_state == "final":
        if role_slot == "arbitrator":
            if grade_created_at:
                # Check if the grade was submitted within the last 6 hours
                six_hours_ago = datetime.now(timezone.utc) - timedelta(hours=6)
                # Handle timezone-naive datetime
                if grade_created_at.tzinfo is None:
                    grade_created_at = grade_created_at.replace(tzinfo=timezone.utc)
                
                if grade_created_at >= six_hours_ago:
                    return True, "Eligible for revision (arbitrator grade submitted within 6 hours)"
                else:
                    return False, "Cannot revise arbitrator grade after 6 hours have passed."
            else:
                return False, "Cannot revise arbitrator grade: grade creation time not available."
        else:
            return False, "This task is finalized and cannot be revised."
    
    # For non-final tasks, eligibility depends on the role and task state
    if role_slot == "resident":
        # Resident can revise their grade at any point before finalization
        return True, "Eligible for revision (resident)"
    elif role_slot == "faculty":
        # Faculty can revise their grade at any point before finalization
        return True, "Eligible for revision (faculty)"
    elif role_slot == "arbitrator":
        # Arbitrator can revise if task is in arbitration state OR if their grade was submitted in the last 6 hours
        if task_state == "arbitration":
            return True, "Eligible for revision (arbitration state)"
        elif grade_created_at:
            # Check if the grade was submitted within the last 6 hours
            six_hours_ago = datetime.now(timezone.utc) - timedelta(hours=6)
            # Handle timezone-naive datetime
            if grade_created_at.tzinfo is None:
                grade_created_at = grade_created_at.replace(tzinfo=timezone.utc)
            
            if grade_created_at >= six_hours_ago:
                return True, "Eligible for revision (arbitrator grade submitted within 6 hours)"
            else:
                return False, "Cannot revise arbitrator grade after 6 hours have passed."
        else:
            return False, "Cannot revise arbitrator grade: grade creation time not available."
    
    return False, f"Unknown role slot: {role_slot}"