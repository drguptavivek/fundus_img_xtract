"""
Utility helpers for selecting intra-rater tasks for a grader.
"""

from __future__ import annotations

from typing import Optional
import logging

from sqlalchemy.orm import Session as OrmSession, selectinload

from models import Session, IntraRaterTask
from services.intra_rater_service import STATE_PENDING

# Set up logger for intra-rater task debugging
intra_rater_logger = logging.getLogger("intra_rater_debug")


def get_next_intra_rater_task(
    user_id: int,
    disease_id: int,
    *,
    db: Optional[OrmSession] = None,
) -> Optional[IntraRaterTask]:
    """
    Return the oldest pending intra-rater task for the grader and disease.

    Args:
        user_id: Identifier of the grader.
        disease_id: Disease filter that must match the original task.
        db: Optional open SQLAlchemy session for reuse.

    Returns:
        The pending IntraRaterTask or None when no task is available.
    """
    close_db = False
    session = db
    if session is None:
        session = Session()
        close_db = True

    try:
        intra_rater_logger.info(f"Searching for intra-rater task - user_id: {user_id}, disease_id: {disease_id}")
        
        # First, let's check if any intra-rater tasks exist for this user at all
        all_user_tasks = (
            session.query(IntraRaterTask)
            .filter(IntraRaterTask.grader_user_id == user_id)
            .all()
        )
        intra_rater_logger.info(f"Total intra-rater tasks for user {user_id}: {len(all_user_tasks)}")
        
        # Check tasks by state
        pending_tasks = [t for t in all_user_tasks if t.state == STATE_PENDING]
        completed_tasks = [t for t in all_user_tasks if t.state != STATE_PENDING]
        intra_rater_logger.info(f"User {user_id} has {len(pending_tasks)} pending, {len(completed_tasks)} completed tasks")
        
        # Check disease-specific tasks
        disease_tasks = (
            session.query(IntraRaterTask)
            .filter(
                IntraRaterTask.grader_user_id == user_id,
                IntraRaterTask.disease_id == disease_id,
            )
            .all()
        )
        intra_rater_logger.info(f"User {user_id} has {len(disease_tasks)} total tasks for disease {disease_id}")
        
        disease_pending_tasks = [t for t in disease_tasks if t.state == STATE_PENDING]
        intra_rater_logger.info(f"User {user_id} has {len(disease_pending_tasks)} pending tasks for disease {disease_id}")
        
        task = (
            session.query(IntraRaterTask)
            .options(
                selectinload(IntraRaterTask.disease),
                selectinload(IntraRaterTask.lab_unit),
                selectinload(IntraRaterTask.batch),
            )
            .filter(
                IntraRaterTask.grader_user_id == user_id,
                IntraRaterTask.disease_id == disease_id,
                IntraRaterTask.state == STATE_PENDING,
            )
            .order_by(IntraRaterTask.created_at.asc(), IntraRaterTask.id.asc())
            .first()
        )

        if task:
            intra_rater_logger.info(f"Found intra-rater task: ID={task.id}, UUID={task.uuid}, created_at={task.created_at}")
        else:
            intra_rater_logger.warning(f"No intra-rater task found for user_id={user_id}, disease_id={disease_id}")

        if task and close_db:
            # Detach so callers can access the identity after closing the helper-owned session.
            session.expunge(task)
        return task
    finally:
        if close_db:
            session.close()
