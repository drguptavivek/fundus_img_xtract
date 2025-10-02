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
from models import Session, GradingTask, Grade, Consensus, User, DiseaseGrading, Disease
import logging
from datetime import datetime


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
    close_db = False
    if db is None:
        db = Session()
        close_db = True
        
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
        faculty_grade = next((g for g in all_grades if g.role_slot == "faculty"), None)
        arbitrator_grade = next((g for g in all_grades if g.role_slot == "arbitrator"), None)
        
        # Check if consensus already exists
        existing_consensus = db.query(Consensus).filter(Consensus.task_id == task.id).first()
        
        if existing_consensus:
            # Consensus already exists, return it
            return existing_consensus
            
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
        elif resident_grade and faculty_grade:
            # Both resident and faculty have graded - check for match
            if resident_grade.disease_grading_id == faculty_grade.disease_grading_id:
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
            db.add(consensus)
            db.flush()  # Ensure the consensus gets an ID without committing transaction
            if close_db:
                db.commit()
                db.refresh(consensus)  # Refresh to get fresh data when managing our own session
            # For shared sessions, we don't refresh since the calling function will commit later
            # The consensus object with its ID is still valid to return
        else:
            # If no consensus was created, still return None
            pass
            
        return consensus
    except Exception as e:
        consensus_logger.exception(f"Failed to create/update consensus for task {task_id}: {e}")
        if db and close_db:
            db.rollback()
        return None
    finally:
        if close_db:
            db.close()


def get_task_consensus_status(task_id: int, db=None) -> dict:
    """
    Get the consensus status for a task.
    
    Args:
        task_id: The ID of the task to check
        db: Optional database session (if not provided, a new session will be created)
        
    Returns:
        Dictionary with consensus status information
    """
    close_db = False
    if db is None:
        db = Session()
        close_db = True
        
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
        faculty_grade = next((g for g in all_grades if g.role_slot == "faculty"), None)
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
            "faculty_grade": {
                "id": faculty_grade.id,
                "label_id": faculty_grade.disease_grading_id,
                "label_impression": faculty_grade.label.impression if faculty_grade and faculty_grade.label else None,
                "grader": faculty_grade.grader.username if faculty_grade and faculty_grade.grader else None,
                "created_at": faculty_grade.created_at if faculty_grade else None
            } if faculty_grade else None,
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
                (resident_grade and faculty_grade and resident_grade.disease_grading_id == faculty_grade.disease_grading_id) or
                arbitrator_grade
            )
        }
    except Exception as e:
        consensus_logger.exception(f"Failed to get consensus status for task {task_id}: {e}")
        return {"error": f"Failed to get consensus status: {e}"}
    finally:
        if close_db:
            db.close()


def update_task_state_based_on_grades(task_id: int, db=None) -> Optional[GradingTask]:
    """
    Update the task state based on the current grades.
    
    Args:
        task_id: The ID of the task to update
        db: Optional database session (if not provided, a new session will be created)
        
    Returns:
        Updated GradingTask object or None if task not found
    """
    close_db = False
    if db is None:
        db = Session()
        close_db = True
        
    try:
        task = db.query(GradingTask).filter(GradingTask.id == task_id).first()
        if not task:
            return None
            
        # Get all grades for this task
        all_grades = db.query(Grade).filter(Grade.task_id == task_id).all()
        
        # Check for grades by role
        resident_grade = next((g for g in all_grades if g.role_slot == "resident"), None)
        faculty_grade = next((g for g in all_grades if g.role_slot == "faculty"), None)
        arbitrator_grade = next((g for g in all_grades if g.role_slot == "arbitrator"), None)
        
        # Log current state and grades for debugging
        consensus_logger.debug(f"Task {task_id} state update: current_state={task.state}, resident_grade={resident_grade is not None}, faculty_grade={faculty_grade is not None}, arbitrator_grade={arbitrator_grade is not None}")
        
        # Determine new state
        if arbitrator_grade:
            # Arbitrator has graded - finalize task
            new_state = "final"
        elif resident_grade and faculty_grade:
            # Both grades submitted, check for match
            if resident_grade.disease_grading_id == faculty_grade.disease_grading_id:
                # Match - finalize task
                new_state = "final"
            else:
                # No match - go to arbitration
                new_state = "arbitration"
        elif resident_grade and not faculty_grade:
            new_state = "resident_done"
        elif faculty_grade and not resident_grade:
            new_state = "faculty_done"
        else:
            new_state = "pending"
        
        # Only update if state actually changed
        if task.state != new_state:
            old_state = task.state
            task.state = new_state
            consensus_logger.info(f"Task {task_id} state updated from '{old_state}' to '{new_state}'")
            
            # Explicitly mark the task as modified to ensure changes are persisted
            from sqlalchemy import inspect
            db.add(task)  # Re-add to session to ensure changes are tracked
        
        # Always commit if this function is managing its own session
        if close_db:
            db.commit()
        else:
            # If using shared session, rely on calling function to commit,
            # but still make sure changes are flushed to be visible to following operations
            db.flush()
            
        db.refresh(task)
        
        return task
    except Exception as e:
        consensus_logger.exception(f"Failed to update task state for task {task_id}: {e}")
        if db and close_db:
            db.rollback()
        return None
    finally:
        if close_db:
            db.close()


def has_consensus(task_id: int, db=None) -> bool:
    """
    Check if a task has reached consensus.
    
    Args:
        task_id: The ID of the task to check
        db: Optional database session (if not provided, a new session will be created)
        
    Returns:
        True if the task has consensus, False otherwise
    """
    close_db = False
    if db is None:
        db = Session()
        close_db = True
        
    try:
        consensus = db.query(Consensus).filter(Consensus.task_id == task_id).first()
        return consensus is not None
    except Exception as e:
        consensus_logger.exception(f"Failed to check consensus for task {task_id}: {e}")
        return False
    finally:
        if close_db:
            db.close()


def get_consensus_method(task_id: int, db=None) -> Optional[str]:
    """
    Get the consensus method for a task (match or adjudication).
    
    Args:
        task_id: The ID of the task to check
        db: Optional database session (if not provided, a new session will be created)
        
    Returns:
        Method string ('match' or 'adjudication') or None if no consensus
    """
    close_db = False
    if db is None:
        db = Session()
        close_db = True
        
    try:
        consensus = db.query(Consensus).filter(Consensus.task_id == task_id).first()
        return consensus.method if consensus else None
    except Exception as e:
        consensus_logger.exception(f"Failed to get consensus method for task {task_id}: {e}")
        return None
    finally:
        if close_db:
            db.close()
