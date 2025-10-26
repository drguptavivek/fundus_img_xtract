"""
Utility helpers for selecting intra-rater tasks for a grader.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session as OrmSession, selectinload

from uuid import uuid4

from models import Session, IntraRaterTask
from services.intra_rater_service import STATE_PENDING


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

        if task and not task.uuid:
            task.uuid = str(uuid4())
            session.add(task)
            session.flush()

        if task and close_db:
            # Detach so callers can access the identity after closing the helper-owned session.
            session.expunge(task)
        return task
    finally:
        if close_db:
            session.close()
