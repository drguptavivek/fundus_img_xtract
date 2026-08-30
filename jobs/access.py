"""Small, shared default visibility contract for durable background jobs."""

from __future__ import annotations

from collections.abc import Collection

from sqlalchemy import and_, false, or_, true

from models import Job

OWNER_ONLY_JOB_TYPES = frozenset({"dataset_export", "discrepancy_export"})


def job_visible_to_actor(
    job: Job,
    *,
    user_id: int,
    is_admin: bool,
    allowed_lab_unit_ids: Collection[int],
) -> bool:
    """Apply the default owner/admin/Lab Unit job visibility rule."""
    if is_admin:
        return True
    if job.uploader_user_id == user_id:
        return True
    if (
        job.project_id is not None
        or job.upload_type in OWNER_ONLY_JOB_TYPES
        or job.lab_unit_id is None
    ):
        return False
    return job.lab_unit_id in set(allowed_lab_unit_ids)


def visible_jobs_predicate(
    *,
    user_id: int,
    is_admin: bool,
    allowed_lab_unit_ids: Collection[int],
):
    """SQL equivalent of :func:`job_visible_to_actor` for list queries."""
    if is_admin:
        return true()
    lab_ids = tuple(set(allowed_lab_unit_ids))
    scoped_labs = Job.lab_unit_id.in_(lab_ids) if lab_ids else false()
    return or_(
        Job.uploader_user_id == user_id,
        and_(
            Job.project_id.is_(None),
            Job.lab_unit_id.is_not(None),
            or_(
                Job.upload_type.is_(None),
                Job.upload_type.not_in(OWNER_ONLY_JOB_TYPES),
            ),
            scoped_labs,
        ),
    )
