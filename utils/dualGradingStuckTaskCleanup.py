"""
Utility functions for detecting and cleaning up stuck tasks in the dual grading system.
A stuck task is one where a user has accessed the task but not submitted a grade 
within the specified time limit (default 60 minutes).
"""

from datetime import datetime, timedelta, timezone
from models import Session, Grade, TaskTracker
from sqlalchemy import and_
import logging


def cleanup_stuck_tasks(time_limit_minutes: int = 60) -> int:
    """
    Identifies and cleans up tasks that have been started but not completed within the specified time limit.
    This helps to reclaim tasks from users who may have disconnected or left tasks incomplete.
    
    Args:
        time_limit_minutes: The time limit in minutes after which a task is considered stuck
        
    Returns:
        The number of stuck tasks that were cleaned up
    """
    db = Session()
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
            logging.info(f"Resetting stuck task: Task ID {tracker.task_id}, "
                        f"Started at {tracker.started_at}, assigned to user {tracker.user_id}")
            # In this implementation, we're just logging; in a full implementation
            # we might want to actually delete the tracker record
            cleaned_up_count += 1
        
        # Return the count of stuck tasks found
        return cleaned_up_count
        
    except Exception as e:
        logging.error(f"Error during stuck task cleanup: {str(e)}")
        return 0
    finally:
        db.close()


def mark_task_started(task_id: int, user_id: int, role_slot: str) -> bool:
    """
    Marks that a user has started working on a task by creating a TaskTracker record.
    This function should be called when a user accesses a task for grading.
    
    Args:
        task_id: The ID of the task being worked on
        user_id: The ID of the user starting the task
        role_slot: The role slot ('resident', 'faculty', or 'arbitrator')
        
    Returns:
        True if successfully marked, False otherwise
    """
    db = Session()
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
            db.commit()
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
            db.commit()
            return True
            
    except IntegrityError:
        # Handle potential race condition where two requests try to create the same tracker
        db.rollback()
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
                db.commit()
                return True
            else:
                return False
        except Exception as e:
            logging.error(f"Error handling duplicate task tracker: {str(e)}")
            return False
    except Exception as e:
        logging.error(f"Error marking task started: {str(e)}")
        db.rollback()
        return False
    finally:
        db.close()


def cleanup_task_tracker(task_id: int, user_id: int, role_slot: str) -> bool:
    """
    Immediately cleanup the TaskTracker record when a task for a specific slot is completed.
    
    Args:
        task_id: The ID of the task being completed
        user_id: The ID of the user completing the task
        role_slot: The role slot ('resident', 'faculty', or 'arbitrator') being completed
        
    Returns:
        True if successfully cleaned up, False otherwise
    """
    db = Session()
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
            db.commit()
            logging.info(f"Cleaned up task tracker - Task ID: {task_id}, "
                        f"User ID: {user_id}, "
                        f"Role: {role_slot}")
            return True
        else:
            logging.info(f"No task tracker found to cleanup - Task ID: {task_id}, "
                        f"User ID: {user_id}, "
                        f"Role: {role_slot}")
            return True  # Consider it successful if no record exists to cleanup
            
    except Exception as e:
        logging.error(f"Error during task tracker cleanup: {str(e)}")
        db.rollback()
        return False
    finally:
        db.close()


def reset_stuck_tasks(time_limit_minutes: int = 60) -> int:
    """
    Identifies and resets tasks that have been started but not completed within the time limit.
    This deletes the tracker records so the tasks become available for other users.
    
    Args:
        time_limit_minutes: The time limit in minutes after which a task is considered stuck
        
    Returns:
        The number of stuck tasks that were reset
    """
    db = Session()
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
            logging.info(f"Reset stuck task - Task ID: {tracker.task_id}, "
                        f"User ID: {tracker.user_id}, "
                        f"Role: {tracker.role_slot}, "
                        f"Started at: {tracker.started_at}")
            db.delete(tracker)
            reset_count += 1
        
        # Commit the changes to reset the stuck tasks
        if stuck_trackers:
            db.commit()
        
        return reset_count
        
    except Exception as e:
        logging.error(f"Error during stuck task reset: {str(e)}")
        db.rollback()
        return 0
    finally:
        db.close()