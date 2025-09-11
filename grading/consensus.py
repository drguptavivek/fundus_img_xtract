from flask import current_app
from sqlalchemy import and_
from models import Session, GradingTask, Grade, Consensus, DiseaseGrading


def create_consensus_for_task(task_id, db=None):
    """
    Create consensus for a task based on the grades.
    
    Args:
        task_id: The ID of the task to create consensus for
        db: Optional database session (if not provided, a new session will be created)
        
    Returns:
        Consensus object or None if consensus cannot be created
    """
    close_db = False
    if db is None:
        db = Session()
        close_db = True
        
    try:
        task = db.query(GradingTask).filter(GradingTask.id == task_id).first()
        if not task:
            return None
            
        # Fetch all grades for this task
        all_grades = db.query(Grade).filter(Grade.task_id == task.id).all()
        
        # Check if we have resident and faculty grades
        resident_grade = next((g for g in all_grades if g.role_slot == "resident"), None)
        faculty_grade = next((g for g in all_grades if g.role_slot == "faculty"), None)
        arbitrator_grade = next((g for g in all_grades if g.role_slot == "arbitrator"), None)
        
        # Check if consensus already exists
        existing_consensus = db.query(Consensus).filter(Consensus.task_id == task.id).first()
        if existing_consensus:
            return existing_consensus
            
        consensus = None
        
        # Determine consensus based on available grades
        # We should create consensus when we have both resident and faculty grades, regardless of task state
        if arbitrator_grade:
            # Arbitrator has graded - use their grade
            consensus = Consensus(
                task_id=task.id,
                final_disease_grading_id=arbitrator_grade.disease_grading_id,
                method="arbitration",
                decided_by_user_id=arbitrator_grade.grader_user_id
            )
        elif resident_grade and faculty_grade:
            # Both grades submitted, check for match
            if resident_grade.disease_grading_id == faculty_grade.disease_grading_id:
                # Match - use the matching grade
                consensus = Consensus(
                    task_id=task.id,
                    final_disease_grading_id=resident_grade.disease_grading_id,
                    method="match",
                    decided_by_user_id=None  # System decision
                )
            # If no match, consensus cannot be created yet - need arbitration
        elif resident_grade and not faculty_grade:
            # Only resident has graded - no consensus yet
            pass
        elif faculty_grade and not resident_grade:
            # Only faculty has graded - no consensus yet
            pass
            
        if consensus:
            db.add(consensus)
            db.commit()
            db.refresh(consensus)
            
        return consensus
    except Exception as e:
        current_app.logger.exception("Failed to create consensus for task %s: %s", task_id, e)
        db.rollback()
        return None
    finally:
        if close_db:
            db.close()


def get_consensus_for_task(task_id, db=None):
    """
    Get the consensus for a task.
    
    Args:
        task_id: The ID of the task to get consensus for
        db: Optional database session (if not provided, a new session will be created)
        
    Returns:
        Consensus object or None if no consensus exists
    """
    close_db = False
    if db is None:
        db = Session()
        close_db = True
        
    try:
        consensus = db.query(Consensus).filter(Consensus.task_id == task_id).first()
        return consensus
    except Exception as e:
        current_app.logger.exception("Failed to get consensus for task %s: %s", task_id, e)
        return None
    finally:
        if close_db:
            db.close()