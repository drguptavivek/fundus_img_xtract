from flask import current_app
from sqlalchemy import and_
from models import Session, GradingTask, Grade, Consensus, DiseaseGrading
from utils.dualGradingConsensusUtils import create_or_update_consensus, update_task_state_based_on_grades


def create_consensus_for_task(task_id, db=None):
    """
    Create consensus for a task based on the grades.
    
    Args:
        task_id: The ID of the task to create consensus for
        db: Optional database session (if not provided, a new session will be created)
        
    Returns:
        Consensus object or None if consensus cannot be created
    """
    return create_or_update_consensus(task_id, db)


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


def update_task_state_after_grading(task_id, db=None):
    """
    Update task state after a grade has been submitted.
    
    Args:
        task_id: The ID of the task to update
        db: Optional database session (if not provided, a new session will be created)
        
    Returns:
        Updated task object or None if task not found
    """
    return update_task_state_based_on_grades(task_id, db)