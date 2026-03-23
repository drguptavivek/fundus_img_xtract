"""
Utility functions for handling consensus in the dual grading system.

This module provides functions for:
- Creating consensus records when grading tasks reach agreement
- Checking consensus status for tasks
- Updating task states based on grading activity 
"""

from typing import Optional, Tuple
from sqlalchemy.orm import selectinload
from sqlalchemy import and_, or_
from models import GradingTask, Grade, Consensus, User, DiseaseGrading, Disease
import logging
from datetime import datetime
from db_transaction_manager import transaction_scope
from utils.log_sanitize import sanitize_log_value


consensus_logger = logging.getLogger("consensus")


def create_or_update_consensus(task_id: int, db=None) -> Optional[Consensus]:
    """
    Create or update consensus for a task based on grades.
    
    Args:
        task_id: The ID of the task to create/update consensus for
        db: Optional database session (if not provided, a new session will be created)
        
    Returns:
        Consensus object if created/updated, None otherwise
    """
    # If db is provided, use it directly (dependency injection pattern)
    if db is not None:
        return _create_or_update_consensus_with_session(task_id, db)
    
    # Otherwise, use the context manager pattern
    with transaction_scope() as db:
        return _create_or_update_consensus_with_session(task_id, db)


def _create_or_update_consensus_with_session(task_id: int, db) -> Optional[Consensus]:
    """
    Internal function that creates or updates consensus using an existing session.
    
    Args:
        task_id: The ID of the task to create/update consensus for
        db: Database session
        
    Returns:
        Consensus object if created/updated, None otherwise
    """
    try:
        task = db.query(GradingTask).options(
            selectinload(GradingTask.grades).selectinload(Grade.grader)
        ).filter(GradingTask.id == task_id).first()
        
        if not task:
            return None
            
        # Get all grades for this task
        all_grades = task.grades
        
        # Check for grades by role
        resident_grade = next((g for g in all_grades if g.role_slot == "resident"), None)
        resident2_grade = next((g for g in all_grades if g.role_slot == "resident2"), None)
        arbitrator_grade = next((g for g in all_grades if g.role_slot == "arbitrator"), None)
        
        # Existing consensus may need to be updated or removed after a revision.
        existing_consensus = db.query(Consensus).filter(Consensus.task_id == task.id).first()
            
        # Determine if consensus can be established
        consensus = None
        
        if arbitrator_grade:
            # An arbitrator has graded, so use adjudication method
            # Fetch the disease and grade information to populate denormalized fields
            final_disease_grading = db.query(DiseaseGrading).filter(DiseaseGrading.id == arbitrator_grade.disease_grading_id).first()
            final_disease = None
            if final_disease_grading:
                final_disease = db.query(Disease).filter(Disease.id == final_disease_grading.disease_id).first()
                
            consensus = Consensus(
                task_id=task.id,
                final_disease_grading_id=arbitrator_grade.disease_grading_id,
                method="adjudication",
                decided_by_user_id=arbitrator_grade.grader_user_id,
                final_disease_name=final_disease.name if final_disease else None,
                final_grade_name=final_disease_grading.impression if final_disease_grading else None,
                final_grade_description=final_disease_grading.guidelines if final_disease_grading else None
            )
        elif resident_grade and resident2_grade:
            # Both resident and resident2 have graded - check for match
            if resident_grade.disease_grading_id == resident2_grade.disease_grading_id:
                # Labels match, create match consensus
                # Fetch the disease and grade information to populate denormalized fields
                final_disease_grading = db.query(DiseaseGrading).filter(DiseaseGrading.id == resident_grade.disease_grading_id).first()
                final_disease = None
                if final_disease_grading:
                    final_disease = db.query(Disease).filter(Disease.id == final_disease_grading.disease_id).first()
                
                consensus = Consensus(
                    task_id=task.id,
                    final_disease_grading_id=resident_grade.disease_grading_id,
                    method="match",
                    decided_by_user_id=None,  # System decision
                    final_disease_name=final_disease.name if final_disease else None,
                    final_grade_name=final_disease_grading.impression if final_disease_grading else None,
                    final_grade_description=final_disease_grading.guidelines if final_disease_grading else None
                )
            # If they don't match, no consensus is created yet - needs arbitration
        
        if consensus:
            if existing_consensus:
                existing_consensus.final_disease_grading_id = consensus.final_disease_grading_id
                existing_consensus.method = consensus.method
                existing_consensus.decided_by_user_id = consensus.decided_by_user_id
                existing_consensus.final_disease_name = consensus.final_disease_name
                existing_consensus.final_grade_name = consensus.final_grade_name
                existing_consensus.final_grade_description = consensus.final_grade_description
                consensus = existing_consensus
            else:
                db.add(consensus)
                db.flush()  # Ensure the consensus gets an ID without committing transaction

            # Log consensus creation with task details
            consensus_logger.info(
                "Consensus created [Task ID: %s] [Method: %s] [Disease ID: %s] [Final Grade ID: %s]",
                sanitize_log_value(task.id),
                sanitize_log_value(consensus.method),
                sanitize_log_value(task.disease_id),
                sanitize_log_value(consensus.final_disease_grading_id),
            )
            
            # Log grade details that contributed to consensus
            if resident_grade:
                consensus_logger.info(
                    "  Resident Grade [ID: %s] [Grade ID: %s] [User ID: %s]",
                    sanitize_log_value(resident_grade.id),
                    sanitize_log_value(resident_grade.disease_grading_id),
                    sanitize_log_value(resident_grade.grader_user_id),
                )
            
            if resident2_grade:
                consensus_logger.info(
                    "  resident2 Grade [ID: %s] [Grade ID: %s] [User ID: %s]",
                    sanitize_log_value(resident2_grade.id),
                    sanitize_log_value(resident2_grade.disease_grading_id),
                    sanitize_log_value(resident2_grade.grader_user_id),
                )
            
            if arbitrator_grade:
                consensus_logger.info(
                    "  Arbitrator Grade [ID: %s] [Grade ID: %s] [User ID: %s]",
                    sanitize_log_value(arbitrator_grade.id),
                    sanitize_log_value(arbitrator_grade.disease_grading_id),
                    sanitize_log_value(arbitrator_grade.grader_user_id),
                )
            
            # Refresh to get fresh data
            db.refresh(consensus)
        else:
            if existing_consensus:
                db.delete(existing_consensus)
                db.flush()
            return None
            
        return consensus
    except Exception as e:
        consensus_logger.exception(
            "Failed to create/update consensus for task %s: %s",
            sanitize_log_value(task_id),
            sanitize_log_value(e),
        )
        raise


def get_task_consensus_status(task_id: int, db=None) -> dict:
    """
    Get the consensus status for a task.
    
    Args:
        task_id: The ID of the task to check
        db: Optional database session (if not provided, a new session will be created)
        
    Returns:
        Dictionary with consensus status information
    """
    # If db is provided, use it directly (dependency injection pattern)
    if db is not None:
        return _get_task_consensus_status_with_session(task_id, db)
    
    # Otherwise, use the context manager pattern
    with transaction_scope() as db:
        return _get_task_consensus_status_with_session(task_id, db)


def _get_task_consensus_status_with_session(task_id: int, db) -> dict:
    """
    Internal function that gets consensus status using an existing session.
    
    Args:
        task_id: The ID of the task to check
        db: Database session
        
    Returns:
        Dictionary with consensus status information
    """
    try:
        task = db.query(GradingTask).options(
            selectinload(GradingTask.grades).selectinload(Grade.grader),
            selectinload(GradingTask.consensus).selectinload(Consensus.decided_by),
            selectinload(GradingTask.consensus).selectinload(Consensus.final_label)
        ).filter(GradingTask.id == task_id).first()
        
        if not task:
            return {"error": "Task not found"}
            
        # Get all grades for this task
        all_grades = task.grades
        
        # Check for grades by role
        resident_grade = next((g for g in all_grades if g.role_slot == "resident"), None)
        resident2_grade = next((g for g in all_grades if g.role_slot == "resident2"), None)
        arbitrator_grade = next((g for g in all_grades if g.role_slot == "arbitrator"), None)
        
        # Check for existing consensus
        existing_consensus = task.consensus
        
        return {
            "task_id": task.id,
            "task_state": task.state,
            "resident_grade": {
                "id": resident_grade.id,
                "label_id": resident_grade.disease_grading_id,
                "label_impression": resident_grade.label.impression if resident_grade and resident_grade.label else None,
                "grader": resident_grade.grader.username if resident_grade and resident_grade.grader else None,
                "created_at": resident_grade.created_at if resident_grade else None
            } if resident_grade else None,
            "resident2_grade": {
                "id": resident2_grade.id,
                "label_id": resident2_grade.disease_grading_id,
                "label_impression": resident2_grade.label.impression if resident2_grade and resident2_grade.label else None,
                "grader": resident2_grade.grader.username if resident2_grade and resident2_grade.grader else None,
                "created_at": resident2_grade.created_at if resident2_grade else None
            } if resident2_grade else None,
            "arbitrator_grade": {
                "id": arbitrator_grade.id,
                "label_id": arbitrator_grade.disease_grading_id,
                "label_impression": arbitrator_grade.label.impression if arbitrator_grade and arbitrator_grade.label else None,
                "grader": arbitrator_grade.grader.username if arbitrator_grade and arbitrator_grade.grader else None,
                "created_at": arbitrator_grade.created_at if arbitrator_grade else None
            } if arbitrator_grade else None,
            "consensus": {
                "id": existing_consensus.id,
                "method": existing_consensus.method,
                "final_label_id": existing_consensus.final_disease_grading_id,
                "final_label_impression": existing_consensus.final_label.impression if existing_consensus and existing_consensus.final_label else None,
                "decided_by_user_id": existing_consensus.decided_by_user_id,
                "decided_by_username": existing_consensus.decided_by.username if existing_consensus and existing_consensus.decided_by else None,
                "decided_at": existing_consensus.decided_at
            } if existing_consensus else None,
            "can_create_consensus": bool(
                (resident_grade and resident2_grade and resident_grade.disease_grading_id == resident2_grade.disease_grading_id) or
                arbitrator_grade
            )
        }
    except Exception as e:
        consensus_logger.exception(
            "Failed to get consensus status for task %s: %s",
            sanitize_log_value(task_id),
            sanitize_log_value(e),
        )
        return {"error": f"Failed to get consensus status: {e}"}


def update_task_state_based_on_grades(task_id: int, db=None) -> Optional[GradingTask]:
    """
    Update the task state based on the current grades.
    
    Args:
        task_id: The ID of the task to update
        db: Optional database session (if not provided, a new session will be created)
        
    Returns:
        Updated GradingTask object or None if task not found
    """
    # If db is provided, use it directly (dependency injection pattern)
    if db is not None:
        return _update_task_state_based_on_grades_with_session(task_id, db)
    
    # Otherwise, use the context manager pattern
    with transaction_scope() as db:
        return _update_task_state_based_on_grades_with_session(task_id, db)


def _update_task_state_based_on_grades_with_session(task_id: int, db) -> Optional[GradingTask]:
    """
    Internal function that updates task state using an existing session.
    
    Args:
        task_id: The ID of the task to update
        db: Database session
        
    Returns:
        Updated GradingTask object or None if task not found
    """
    try:
        task = db.query(GradingTask).filter(GradingTask.id == task_id).first()
        if not task:
            return None
            
        # Get all grades for this task
        all_grades = db.query(Grade).filter(Grade.task_id == task_id).all()
        
        # Check for grades by role
        resident_grade = next((g for g in all_grades if g.role_slot == "resident"), None)
        resident2_grade = next((g for g in all_grades if g.role_slot == "resident2"), None)
        arbitrator_grade = next((g for g in all_grades if g.role_slot == "arbitrator"), None)
        
        # Log current state and grades for debugging
        consensus_logger.debug(
            "Task %s state update: current_state=%s, resident_grade=%s, resident2_grade=%s, arbitrator_grade=%s",
            sanitize_log_value(task_id),
            sanitize_log_value(task.state),
            sanitize_log_value(resident_grade is not None),
            sanitize_log_value(resident2_grade is not None),
            sanitize_log_value(arbitrator_grade is not None),
        )
        
        # Determine new state
        if arbitrator_grade:
            # Arbitrator has graded - finalize task
            new_state = "final"
        elif resident_grade and resident2_grade:
            # Both grades submitted, check for match
            if resident_grade.disease_grading_id == resident2_grade.disease_grading_id:
                # Match - finalize task
                new_state = "final"
            else:
                # No match - go to arbitration
                new_state = "arbitration"
        elif resident_grade and not resident2_grade:
            new_state = "resident_done"
        elif resident2_grade and not resident_grade:
            new_state = "resident2_done"
        else:
            new_state = "pending"
        
        # Only update if state actually changed
        if task.state != new_state:
            old_state = task.state
            task.state = new_state
            consensus_logger.info(
                "Task %s state updated from '%s' to '%s'",
                sanitize_log_value(task_id),
                sanitize_log_value(old_state),
                sanitize_log_value(new_state),
            )
            
            # Explicitly mark the task as modified to ensure changes are persisted
            from sqlalchemy import inspect
            db.add(task)  # Re-add to session to ensure changes are tracked
        
        # Flush changes to make them visible to following operations
        db.flush()
        db.refresh(task)
        
        return task
    except Exception as e:
        consensus_logger.exception(
            "Failed to update task state for task %s: %s",
            sanitize_log_value(task_id),
            sanitize_log_value(e),
        )
        raise


def has_consensus(task_id: int, db=None) -> bool:
    """
    Check if a task has reached consensus.
    
    Args:
        task_id: The ID of the task to check
        db: Optional database session (if not provided, a new session will be created)
        
    Returns:
        True if the task has consensus, False otherwise
    """
    # If db is provided, use it directly (dependency injection pattern)
    if db is not None:
        return _has_consensus_with_session(task_id, db)
    
    # Otherwise, use the context manager pattern
    with transaction_scope() as db:
        return _has_consensus_with_session(task_id, db)


def _has_consensus_with_session(task_id: int, db) -> bool:
    """
    Internal function that checks consensus using an existing session.
    
    Args:
        task_id: The ID of the task to check
        db: Database session
        
    Returns:
        True if the task has consensus, False otherwise
    """
    try:
        consensus = db.query(Consensus).filter(Consensus.task_id == task_id).first()
        return consensus is not None
    except Exception as e:
        consensus_logger.exception(
            "Failed to check consensus for task %s: %s",
            sanitize_log_value(task_id),
            sanitize_log_value(e),
        )
        return False


def get_consensus_method(task_id: int, db=None) -> Optional[str]:
    """
    Get the consensus method for a task (match, adjudication, or task_review).
    
    Args:
        task_id: The ID of the task to check
        db: Optional database session (if not provided, a new session will be created)
        
    Returns:
        Method string ('match' or 'adjudication') or None if no consensus
    """
    # If db is provided, use it directly (dependency injection pattern)
    if db is not None:
        return _get_consensus_method_with_session(task_id, db)
    
    # Otherwise, use the context manager pattern
    with transaction_scope() as db:
        return _get_consensus_method_with_session(task_id, db)


def _get_consensus_method_with_session(task_id: int, db) -> Optional[str]:
    """
    Internal function that gets consensus method using an existing session.
    
    Args:
        task_id: The ID of the task to check
        db: Database session
        
    Returns:
        Method string ('match', 'adjudication', 'task_review') or None if no consensus
    """
    try:
        consensus = db.query(Consensus).filter(Consensus.task_id == task_id).first()
        return consensus.method if consensus else None
    except Exception as e:
        consensus_logger.exception(
            "Failed to get consensus method for task %s: %s",
            sanitize_log_value(task_id),
            sanitize_log_value(e),
        )
        return None
