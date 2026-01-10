"""
Utility functions for detecting and cleaning up stuck tasks in the dual grading system.
A stuck task is one where a user has accessed the task but not submitted a grade 
within the specified time limit (default 60 minutes). 
"""

from datetime import datetime, timedelta, timezone
from models import Grade, TaskTracker
from sqlalchemy import and_
import logging
from db_transaction_manager import transaction_scope
from utils.log_sanitize import sanitize_log_value


def cleanup_stuck_tasks(time_limit_minutes: int = 60, db=None) -> int:
    """
    Identifies and cleans up tasks that have been started but not completed within the specified time limit.
    This helps to reclaim tasks from users who may have disconnected or left tasks incomplete.
    
    Args:
        time_limit_minutes: The time limit in minutes after which a task is considered stuck
        db: Optional database session (if not provided, a new session will be created)
        
    Returns:
        The number of stuck tasks that were cleaned up
    """
    # If db is provided, use it directly (dependency injection pattern)
    if db is not None:
        return _cleanup_stuck_tasks_with_session(time_limit_minutes, db)
    
    # Otherwise, use the context manager pattern
    with transaction_scope() as db:
        return _cleanup_stuck_tasks_with_session(time_limit_minutes, db)


def _cleanup_stuck_tasks_with_session(time_limit_minutes: int, db) -> int:
    """
    Internal function that cleans up stuck tasks using an existing session.
    
    Args:
        time_limit_minutes: The time limit in minutes after which a task is considered stuck
        db: Database session
        
    Returns:
        The number of stuck tasks that were cleaned up
    """
    try:
        # Calculate the time threshold
        time_threshold = datetime.now(timezone.utc) - timedelta(minutes=time_limit_minutes)
        
        # Find task tracker entries where task was started but not completed (no grade exists) 
        # and the start time is older than the threshold
        from sqlalchemy import text
        stuck_tasks = db.query(TaskTracker).filter(
            and_(
                TaskTracker.started_at < time_threshold,  # Started more than time_limit_minutes ago
            )
        ).all()
        
        cleaned_up_count = 0
        for tracker in stuck_tasks:
            # We can log the stuck task for auditing purposes
            logging.info(
                "Resetting stuck task: Task ID %s, Started at %s, assigned to user %s",
                sanitize_log_value(tracker.task_id),
                sanitize_log_value(tracker.started_at),
                sanitize_log_value(tracker.user_id),
            )
            # In this implementation, we're just logging; in a full implementation
            # we might want to actually delete the tracker record
            cleaned_up_count += 1
        
        # Return the count of stuck tasks found
        return cleaned_up_count
        
    except Exception as e:
        logging.error(
            "Error during stuck task cleanup: %s",
            sanitize_log_value(e),
        )
        raise


def mark_task_started(task_id: int, user_id: int, role_slot: str, db=None) -> bool:
    """
    Marks that a user has started working on a task by creating a TaskTracker record.
    This function should be called when a user accesses a task for grading.
    
    Args:
        task_id: The ID of the task being worked on
        user_id: The ID of the user starting the task
        role_slot: The role slot ('resident', 'resident2', or 'arbitrator')
        db: Optional database session (if not provided, a new session will be created)
        
    Returns:
        True if successfully marked, False otherwise
    """
    # If db is provided, use it directly (dependency injection pattern)
    if db is not None:
        return _mark_task_started_with_session(task_id, user_id, role_slot, db)
    
    # Otherwise, use the context manager pattern
    with transaction_scope() as db:
        return _mark_task_started_with_session(task_id, user_id, role_slot, db)


def _mark_task_started_with_session(task_id: int, user_id: int, role_slot: str, db) -> bool:
    """
    Internal function that marks a task as started using an existing session.
    
    Args:
        task_id: The ID of the task being worked on
        user_id: The ID of the user starting the task
        role_slot: The role slot ('resident', 'resident2', or 'arbitrator')
        db: Database session
        
    Returns:
        True if successfully marked, False otherwise
    """
    try:
        from sqlalchemy.exc import IntegrityError
        
        # Check if a tracker record already exists for this user and task
        existing_tracker = db.query(TaskTracker).filter(
            and_(
                TaskTracker.task_id == task_id,
                TaskTracker.user_id == user_id,
                TaskTracker.role_slot == role_slot
            )
        ).first()
        
        if existing_tracker:
            # Update the existing tracker's start time
            existing_tracker.started_at = datetime.now(timezone.utc)
            return True
        else:
            # Create a new tracker record
            tracker = TaskTracker(
                task_id=task_id,
                user_id=user_id,
                role_slot=role_slot,
                started_at=datetime.now(timezone.utc)
            )
            db.add(tracker)
            return True
            
    except IntegrityError:
        # Handle potential race condition where two requests try to create the same tracker
        # Try to update the existing record
        try:
            existing_tracker = db.query(TaskTracker).filter(
                and_(
                    TaskTracker.task_id == task_id,
                    TaskTracker.user_id == user_id,
                    TaskTracker.role_slot == role_slot
                )
            ).first()
            if existing_tracker:
                existing_tracker.started_at = datetime.now(timezone.utc)
                return True
            else:
                return False
        except Exception as e:
            logging.error(
                "Error handling duplicate task tracker: %s",
                sanitize_log_value(e),
            )
            return False
    except Exception as e:
        logging.error(
            "Error marking task started: %s",
            sanitize_log_value(e),
        )
        raise


def cleanup_task_tracker(task_id: int, user_id: int, role_slot: str, db=None) -> bool:
    """
    Immediately cleanup the TaskTracker record when a task for a specific slot is completed.
    
    Args:
        task_id: The ID of the task being completed
        user_id: The ID of the user completing the task
        role_slot: The role slot ('resident', 'resident2', or 'arbitrator') being completed
        db: Optional database session (if not provided, a new session will be created)
        
    Returns:
        True if successfully cleaned up, False otherwise
    """
    # If db is provided, use it directly (dependency injection pattern)
    if db is not None:
        return _cleanup_task_tracker_with_session(task_id, user_id, role_slot, db)
    
    # Otherwise, use the context manager pattern
    with transaction_scope() as db:
        return _cleanup_task_tracker_with_session(task_id, user_id, role_slot, db)


def _cleanup_task_tracker_with_session(task_id: int, user_id: int, role_slot: str, db) -> bool:
    """
    Internal function that cleans up a task tracker using an existing session.
    
    Args:
        task_id: The ID of the task being completed
        user_id: The ID of the user completing the task
        role_slot: The role slot ('resident', 'resident2', or 'arbitrator') being completed
        db: Database session
        
    Returns:
        True if successfully cleaned up, False otherwise
    """
    try:
        # Find the specific task tracker record
        tracker = db.query(TaskTracker).filter(
            and_(
                TaskTracker.task_id == task_id,
                TaskTracker.user_id == user_id,
                TaskTracker.role_slot == role_slot
            )
        ).first()
        
        if tracker:
            # Remove the tracker record
            db.delete(tracker)
            logging.info(
                "Cleaned up task tracker - Task ID: %s, User ID: %s, Role: %s",
                sanitize_log_value(task_id),
                sanitize_log_value(user_id),
                sanitize_log_value(role_slot),
            )
            return True
        else:
            logging.info(
                "No task tracker found to cleanup - Task ID: %s, User ID: %s, Role: %s",
                sanitize_log_value(task_id),
                sanitize_log_value(user_id),
                sanitize_log_value(role_slot),
            )
            return False
            
    except Exception as e:
        logging.error(
            "Error during task tracker cleanup: %s",
            sanitize_log_value(e),
        )
        raise


def reset_stuck_tasks(time_limit_minutes: int = 60, db=None) -> int:
    """
    Identifies and resets tasks that have been started but not completed within the time limit.
    This deletes the tracker records so the tasks become available for other users.
    
    Args:
        time_limit_minutes: The time limit in minutes after which a task is considered stuck
        db: Optional database session (if not provided, a new session will be created)
        
    Returns:
        The number of stuck tasks that were reset
    """
    # If db is provided, use it directly (dependency injection pattern)
    if db is not None:
        return _reset_stuck_tasks_with_session(time_limit_minutes, db)
    
    # Otherwise, use the context manager pattern
    with transaction_scope() as db:
        return _reset_stuck_tasks_with_session(time_limit_minutes, db)


def _reset_stuck_tasks_with_session(time_limit_minutes: int, db) -> int:
    """
    Internal function that resets stuck tasks using an existing session.
    
    Args:
        time_limit_minutes: The time limit in minutes after which a task is considered stuck
        db: Database session
        
    Returns:
        The number of stuck tasks that were reset
    """
    try:
        # Calculate the time threshold
        time_threshold = datetime.now(timezone.utc) - timedelta(minutes=time_limit_minutes)
        
        # Find task tracker entries where grading was started but not completed within the time limit
        stuck_trackers = db.query(TaskTracker).filter(
            and_(
                TaskTracker.started_at < time_threshold,
            )
        ).all()
        
        reset_count = 0
        for tracker in stuck_trackers:
            logging.info(
                "Reset stuck task - Task ID: %s, User ID: %s, Role: %s, Started at: %s",
                sanitize_log_value(tracker.task_id),
                sanitize_log_value(tracker.user_id),
                sanitize_log_value(tracker.role_slot),
                sanitize_log_value(tracker.started_at),
            )
            db.delete(tracker)
            reset_count += 1
        
        # Return the count of reset tasks
        return reset_count
        
    except Exception as e:
        logging.error(
            "Error during stuck task reset: %s",
            sanitize_log_value(e),
        )
        raise
