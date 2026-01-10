"""
Utility helpers for selecting intra-rater tasks for a grader.
"""

from __future__ import annotations

from typing import Optional
import logging

from sqlalchemy.orm import Session as OrmSession, selectinload

from models import IntraRaterTask
from services.intra_rater_service import STATE_PENDING
from utils.utils import get_db_session
from utils.log_sanitize import sanitize_log_value

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
        # Use get_db_session context manager when no session provided
        with get_db_session() as new_session:
            return get_next_intra_rater_task(user_id, disease_id, db=new_session)

    try:
        intra_rater_logger.info(
            "Searching for intra-rater task - user_id: %s, disease_id: %s",
            sanitize_log_value(user_id),
            sanitize_log_value(disease_id),
        )
        
        # First, let's check if any intra-rater tasks exist for this user at all
        all_user_tasks = (
            session.query(IntraRaterTask)
            .filter(IntraRaterTask.grader_user_id == user_id)
            .all()
        )
        intra_rater_logger.info(
            "Total intra-rater tasks for user %s: %s",
            sanitize_log_value(user_id),
            sanitize_log_value(len(all_user_tasks)),
        )
        
        # Check tasks by state
        pending_tasks = [t for t in all_user_tasks if t.state == STATE_PENDING]
        completed_tasks = [t for t in all_user_tasks if t.state != STATE_PENDING]
        intra_rater_logger.info(
            "User %s has %s pending, %s completed tasks",
            sanitize_log_value(user_id),
            sanitize_log_value(len(pending_tasks)),
            sanitize_log_value(len(completed_tasks)),
        )
        
        # Check disease-specific tasks
        disease_tasks = (
            session.query(IntraRaterTask)
            .filter(
                IntraRaterTask.grader_user_id == user_id,
                IntraRaterTask.disease_id == disease_id,
            )
            .all()
        )
        intra_rater_logger.info(
            "User %s has %s total tasks for disease %s",
            sanitize_log_value(user_id),
            sanitize_log_value(len(disease_tasks)),
            sanitize_log_value(disease_id),
        )
        
        disease_pending_tasks = [t for t in disease_tasks if t.state == STATE_PENDING]
        intra_rater_logger.info(
            "User %s has %s pending tasks for disease %s",
            sanitize_log_value(user_id),
            sanitize_log_value(len(disease_pending_tasks)),
            sanitize_log_value(disease_id),
        )
        
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
            intra_rater_logger.info(
                "Found intra-rater task: ID=%s, UUID=%s, created_at=%s",
                sanitize_log_value(task.id),
                sanitize_log_value(task.uuid),
                sanitize_log_value(task.created_at),
            )
        else:
            intra_rater_logger.warning(
                "No intra-rater task found for user_id=%s, disease_id=%s",
                sanitize_log_value(user_id),
                sanitize_log_value(disease_id),
            )

        if task and close_db:
            # Detach so callers can access the identity after closing the helper-owned session.
            session.expunge(task)
        return task
    finally:
        if close_db:
            session.close()
