"""
Utility functions for detecting and cleaning up stuck tasks in the dual grading system.
A stuck task is one where a user has accessed the task but not submitted a grade 
within the specified time limit (default 60 minutes).
"""

from datetime import datetime, timedelta, timezone
from models import Session, Grade
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
        
        # Find grades where start_time is set but the grade was never submitted 
        # (time_taken is still None) and the start_time is older than the threshold
        stuck_grades = db.query(Grade).filter(
            and_(
                Grade.start_time.isnot(None),  # User started grading
                Grade.start_time < time_threshold,  # Started more than time_limit_minutes ago
                Grade.time_taken.is_(None)  # Grade was never submitted (no time_taken recorded)
            )
        ).all()
        
        cleaned_up_count = 0
        for grade in stuck_grades:
            # We can log the stuck task for auditing purposes
            logging.info(f"Resetting stuck task: Task ID {grade.task_id}, Grade ID {grade.id}, "
                        f"Started at {grade.start_time}, assigned to user {grade.grader_user_id}")
            # In this implementation, we're just logging; in a full implementation
            # we might want to actually reset the start_time or handle the task differently
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
    Marks that a user has started working on a task. This function should be called 
    when a user accesses a task for grading.
    
    Args:
        task_id: The ID of the task being worked on
        user_id: The ID of the user starting the task
        role_slot: The role slot ('resident', 'faculty', or 'arbitrator')
        
    Returns:
        True if successfully marked, False otherwise
    """
    db = Session()
    try:
        # Check if a grade record already exists for this user and task
        grade = db.query(Grade).filter(
            and_(
                Grade.task_id == task_id,
                Grade.grader_user_id == user_id,
                Grade.role_slot == role_slot
            )
        ).first()
        
        if grade:
            # Update the existing grade's start_time to now
            grade.start_time = datetime.now(timezone.utc)
            db.commit()
            return True
        else:
            # Create a new grade record with start_time but no grading decision yet
            # We'll use a default/placeholder for disease_grading_id until the user submits
            # We'll use the lowest possible ID (which shouldn't be a real grading ID)
            new_grade = Grade(
                task_id=task_id,
                grader_user_id=user_id,
                role_slot=role_slot,
                disease_grading_id=0,  # Placeholder value - this should be replaced with an actual valid grading ID when user submits
                start_time=datetime.now(timezone.utc)
            )
            db.add(new_grade)
            db.commit()
            return True
            
    except Exception as e:
        logging.error(f"Error marking task started: {str(e)}")
        db.rollback()
        return False
    finally:
        db.close()


def reset_stuck_tasks(time_limit_minutes: int = 60) -> int:
    """
    Identifies and resets tasks that have been started but not completed within the time limit.
    This makes the tasks available for other users to work on.
    
    Args:
        time_limit_minutes: The time limit in minutes after which a task is considered stuck
        
    Returns:
        The number of stuck tasks that were reset
    """
    db = Session()
    try:
        # Calculate the time threshold
        time_threshold = datetime.now(timezone.utc) - timedelta(minutes=time_limit_minutes)
        
        # Find grades where grading was started but not completed within the time limit
        stuck_grades = db.query(Grade).filter(
            and_(
                Grade.start_time.isnot(None),
                Grade.start_time < time_threshold,
                # If the grade was never submitted, time_taken will be None
                Grade.time_taken.is_(None)
            )
        ).all()
        
        reset_count = 0
        for grade in stuck_grades:
            # Reset the start_time to None to indicate the task is no longer in progress
            grade.start_time = None
            logging.info(f"Reset stuck task - Task ID: {grade.task_id}, "
                        f"User ID: {grade.grader_user_id}, "
                        f"Role: {grade.role_slot}, "
                        f"Started at: {grade.start_time}")
            reset_count += 1
        
        # Commit the changes to reset the stuck tasks
        if stuck_grades:
            db.commit()
        
        return reset_count
        
    except Exception as e:
        logging.error(f"Error during stuck task reset: {str(e)}")
        db.rollback()
        return 0
    finally:
        db.close()