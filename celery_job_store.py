from typing import List, Optional
from models import Job, JobItem
from db_transaction_manager import transaction_scope

def db_add_job_items(job_token: str, filenames: List[str]) -> None:
    """
    Dynamically adds new items to an existing job.
    Useful for ZIP extraction where 1 input file becomes N output files.
    """
    with transaction_scope() as db:
        job = db.query(Job).filter_by(token=job_token).first()
        if not job:
            return
        
        # Inherit uploader info from the parent job
        items = [
            JobItem(
                job_id=job.id,
                filename=fn,
                state="queued",
                uploader_user_id=job.uploader_user_id,
                uploader_username=job.uploader_username,
                uploader_ip=job.uploader_ip,
            )
            for fn in filenames
        ]
        db.add_all(items)

def check_and_complete_job(job_token: str) -> None:
    """
    Checks if all items in the job are in a terminal state ('ok' or 'error').
    If so, updates the Job status:
    - 'done': All items ok
    - 'error': All items error
    - 'partial_error': Mixed ok/error
    """
    with transaction_scope() as db:
        job = db.query(Job).filter_by(token=job_token).first()
        if not job or job.status in ("done", "error", "partial_error"):
            return

        # Check all items
        items = job.items
        if not items:
            # No items? Mark done.
            job.status = "done"
            return

        # Terminal states
        terminal = {"ok", "error"}
        if not all(item.state in terminal for item in items):
            # Still processing some items
            return

        # All terminal. Determine final status.
        error_count = sum(1 for item in items if item.state == "error")
        total_count = len(items)

        if error_count == 0:
            job.status = "done"
        elif error_count == total_count:
            job.status = "error"
            job.error = "All items failed processing"
        else:
            job.status = "partial_error"
            job.error = f"{error_count}/{total_count} items failed"

