"""Permission-scoped, reusable discrepancy-review queues."""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy.orm import Session

from encounter_sets.permissions import (
    CAPABILITY_DISCREPANCY_REVIEW,
    apply_task_capability_scope,
)
from models import Consensus, GradingTask, Job, JobItem, User

QUEUE_UPLOAD_TYPE = "discrepancy_review_queue"
MAX_CSV_BYTES = 1024 * 1024
MAX_QUEUE_TASKS = 5000
REVIEWABLE_CONSENSUS_METHODS = frozenset({"match", "adjudication", "regrade", "task_review"})


class ReviewQueueError(ValueError):
    """Raised when a review queue cannot be created or accessed."""


@dataclass(frozen=True)
class ReviewQueueDTO:
    token: str
    disease_id: int
    task_ids: tuple[int, ...]


def parse_task_id_csv(content: bytes) -> tuple[int, ...]:
    if not content:
        raise ReviewQueueError("The CSV file is empty.")
    if len(content) > MAX_CSV_BYTES:
        raise ReviewQueueError("The CSV file exceeds the 1 MiB limit.")
    try:
        text_content = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ReviewQueueError("The CSV file must use UTF-8 encoding.") from exc
    reader = csv.DictReader(io.StringIO(text_content))
    normalized = {
        (name or "").strip().lower(): name for name in (reader.fieldnames or [])
    }
    source_column = normalized.get("task_id")
    if source_column is None:
        raise ReviewQueueError("The CSV file must contain a task_id column.")

    task_ids: list[int] = []
    seen: set[int] = set()
    for line_number, row in enumerate(reader, start=2):
        raw_value = (row.get(source_column) or "").strip()
        try:
            task_id = int(raw_value)
        except (TypeError, ValueError) as exc:
            raise ReviewQueueError(f"Invalid task_id on CSV line {line_number}.") from exc
        if task_id <= 0:
            raise ReviewQueueError(f"Invalid task_id on CSV line {line_number}.")
        if task_id not in seen:
            seen.add(task_id)
            task_ids.append(task_id)
        if len(task_ids) > MAX_QUEUE_TASKS:
            raise ReviewQueueError(f"A queue may contain at most {MAX_QUEUE_TASKS} tasks.")
    if not task_ids:
        raise ReviewQueueError("The CSV file contains no task IDs.")
    return tuple(task_ids)


def _authorized_tasks(db: Session, *, user: User, task_ids: tuple[int, ...]):
    query = db.query(GradingTask).filter(GradingTask.id.in_(task_ids))
    return apply_task_capability_scope(
        query,
        GradingTask,
        user,
        CAPABILITY_DISCREPANCY_REVIEW,
    ).all()


def _reviewable_task_ids(db: Session, task_ids: tuple[int, ...]) -> set[int]:
    return {
        task_id
        for (task_id,) in db.query(Consensus.task_id).filter(
            Consensus.task_id.in_(task_ids),
            Consensus.method.in_(REVIEWABLE_CONSENSUS_METHODS),
        ).all()
    }


def create_review_queue(
    db: Session,
    *,
    user: User,
    filename: str,
    content: bytes,
) -> ReviewQueueDTO:
    task_ids = parse_task_id_csv(content)
    tasks = _authorized_tasks(db, user=user, task_ids=task_ids)
    task_by_id = {task.id: task for task in tasks}
    if (
        set(task_by_id) != set(task_ids)
        or _reviewable_task_ids(db, task_ids) != set(task_ids)
    ):
        raise ReviewQueueError("One or more task IDs are unavailable for review.")
    disease_ids = {task.disease_id for task in tasks}
    if len(disease_ids) != 1:
        raise ReviewQueueError("All tasks in a review queue must use the same disease.")

    token = uuid4().hex
    job = Job(
        token=token,
        status="done",
        excel_filename=(filename or "review_queue.csv")[:255],
        upload_type=QUEUE_UPLOAD_TYPE,
        uploader_user_id=user.id,
        uploader_username=user.username,
    )
    db.add(job)
    db.flush()
    db.add_all([
        JobItem(
            job_id=job.id,
            filename=str(task_id),
            state="queued",
            task_id=task_id,
            uploader_user_id=user.id,
            uploader_username=user.username,
        )
        for task_id in task_ids
    ])
    db.flush()
    return ReviewQueueDTO(token, next(iter(disease_ids)), task_ids)


def load_review_queue(db: Session, *, user: User, token: str) -> ReviewQueueDTO:
    job = (
        db.query(Job)
        .filter(
            Job.token == token,
            Job.upload_type == QUEUE_UPLOAD_TYPE,
            Job.uploader_user_id == user.id,
        )
        .first()
    )
    if job is None:
        raise ReviewQueueError("Review queue not found.")
    ordered_ids = tuple(
        task_id
        for (task_id,) in (
            db.query(JobItem.task_id)
            .filter(JobItem.job_id == job.id, JobItem.task_id.isnot(None))
            .order_by(JobItem.id)
            .all()
        )
    )
    tasks = _authorized_tasks(db, user=user, task_ids=ordered_ids)
    task_by_id = {task.id: task for task in tasks}
    if (
        not ordered_ids
        or set(task_by_id) != set(ordered_ids)
        or _reviewable_task_ids(db, ordered_ids) != set(ordered_ids)
    ):
        raise ReviewQueueError("Review queue not found.")
    disease_ids = {task.disease_id for task in tasks}
    if len(disease_ids) != 1:
        raise ReviewQueueError("Review queue not found.")
    return ReviewQueueDTO(job.token, next(iter(disease_ids)), ordered_ids)
