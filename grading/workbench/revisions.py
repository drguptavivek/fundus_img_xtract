"""Revision eligibility owned by the grading workbench."""
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from models import User

from models import Grade, GradingTask
from utils.dualGradingFetchDetailUtils import fetch_existing_grade_for_user


REVISION_WINDOW_HOURS = 24


def _normalize_grade_timestamp(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _is_within_revision_window(grade_created_at: Optional[datetime]) -> bool:
    normalized_created_at = _normalize_grade_timestamp(grade_created_at)
    if normalized_created_at is None:
        return False
    cutoff = datetime.now(timezone.utc) - timedelta(hours=REVISION_WINDOW_HOURS)
    return normalized_created_at >= cutoff


def is_user_eligible_for_revision(db: Session, user_id: int, task_id: int, slot_type: str, grade: Grade = None) -> dict:
    """
    Check if a user is eligible to revise their grade for a specific task and slot.

    Args:
        db: Database session
        user_id: ID of the user requesting revision
        task_id: ID of the grading task
        slot_type: The slot type ('resident', 'resident2', 'arbitrator')
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
    if slot_type not in ['resident', 'resident2', 'arbitrator']:
        result["message"] = f"Invalid slot type: {slot_type}"
        return result

    # Get the grade if not provided
    if grade is None:
        # Fetching user for scoping
        from models import User
        user = db.query(User).filter_by(id=user_id).first()
        grade = fetch_existing_grade_for_user(db, task_id, user_id, slot_type, user=user)

    # Check if grade exists
    if not grade:
        result["message"] = f"No existing grade found for user {user_id} in slot {slot_type} for task {task_id}"
        return result

    # Check if the grade belongs to the current user
    if grade.grader_user_id != user_id:
        result["message"] = "You are not authorized to revise this grade."
        return result

    is_recent = _is_within_revision_window(grade.created_at)
    result["is_recent"] = is_recent

    if is_recent:
        result["eligible"] = True
        result["message"] = f"Eligible for revision (submitted within {REVISION_WINDOW_HOURS} hours)"
    else:
        result["message"] = f"Cannot revise after {REVISION_WINDOW_HOURS} hours have passed."
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
        from models import User
        user = db.query(User).filter_by(id=user_id).first()
        task = fetch_task_with_related_data(db, task_id, user=user)
        if not task:
            return {
                "eligible": False,
                "message": "Task not found.",
                "grade": None
            }

    # Check if user has made an arbitrator grade for this task
    from models import User
    user = db.query(User).filter_by(id=user_id).first()
    arbitrator_grade = fetch_existing_grade_for_user(db, task_id, user_id, 'arbitrator', user=user)

    if not arbitrator_grade:
        return {
            "eligible": False,
            "message": "Arbitrator slot is not available for this task.",
            "grade": None
        }

    # Check if the grade was made recently within the global revision window.
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
        # Check if this user is the arbitrator who made the decision within the revision window.
        arbitrator_grade = next((g for g in task.grades if g.role_slot == 'arbitrator' and g.grader_user_id == user_id), None)
        if arbitrator_grade:
            if _is_within_revision_window(arbitrator_grade.created_at):
                return True, f"Eligible for revision (submitted within {REVISION_WINDOW_HOURS} hours)"
            return False, f"Cannot revise after {REVISION_WINDOW_HOURS} hours have passed."
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

    # We need to fetch the existing grade to verify if it was created within the revision window.
    from models import User
    user = db.query(User).filter_by(id=user_id).first()
    existing_grade_for_check = fetch_existing_grade_for_user(db, task_id, user_id, slot, user=user)

    if existing_grade_for_check:
        is_recent = _is_within_revision_window(existing_grade_for_check.created_at)
        result["is_recent"] = is_recent

        if is_recent:
            result["allowed"] = True
            result["message"] = f"Arbitrator revision allowed (submitted within {REVISION_WINDOW_HOURS} hours)"
        else:
            result["message"] = f"Arbitrator revision not allowed after {REVISION_WINDOW_HOURS} hours have passed."
    else:
        # If there's no existing grade for this arbitrator, it's not a revision
        result["message"] = "No existing grade found for this arbitrator - this is not a revision."

    return result


def check_revision_eligibility_by_task_state(task_state: str, role_slot: str, grade_created_at: Optional[datetime] = None) -> tuple[bool, str]:
    """
    Check if a user is eligible to revise a grade based on the task state and other conditions.

    Args:
        task_state: Current state of the task
        role_slot: Role slot ('resident', 'resident2', 'arbitrator')
        grade_created_at: When the grade was created

    Returns:
        A tuple of (is_eligible: bool, message: str)
    """
    if role_slot not in {"resident", "resident2", "arbitrator"}:
        return False, f"Unknown role slot: {role_slot}"

    if not grade_created_at:
        return False, "Cannot revise grade: grade creation time not available."

    if _is_within_revision_window(grade_created_at):
        return True, f"Eligible for revision (submitted within {REVISION_WINDOW_HOURS} hours)"

    return False, f"Cannot revise after {REVISION_WINDOW_HOURS} hours have passed."
