"""
Package Update Scanner Celery Tasks

Scheduled and on-demand package update scanning using PyPI API.
"""

from celery_app import celery_app
from db_transaction_manager import get_db_session


@celery_app.task(
    name="celery_tasks.tasks.package_update_tasks.run_package_update_scan_task",
    bind=True,
    acks_late=True
)
def run_package_update_scan_task(
    self,
    scan_type: str = "scheduled",
    user_id: int | None = None
) -> dict:
    """
    Run package update scan and store results in database.

    Checks ALL installed Python packages for available updates from PyPI
    (not just security vulnerabilities).

    Args:
        scan_type: "scheduled" (daily at 3 AM) or "on_demand" (manual trigger)
        user_id: User ID who triggered the scan (None for scheduled)

    Returns:
        Dict with scan results including counts and any errors
    """
    from utils.package_update_scanner import scan_package_updates_and_save

    with get_db_session() as db:
        return scan_package_updates_and_save(
            db,
            scan_type=scan_type,
            triggered_by_user_id=user_id
        )


@celery_app.task(
    name="celery_tasks.tasks.package_update_tasks.cleanup_old_package_scans_task",
    bind=True,
    acks_late=True
)
def cleanup_old_package_scans_task(self) -> dict:
    """
    Delete package update scan results older than 200 days.

    This runs daily at 4 AM UTC (1 hour after the update scan).

    Returns:
        Dict with deletion results
    """
    from utils.package_update_scanner import cleanup_old_scans

    with get_db_session() as db:
        return cleanup_old_scans(db, days=200)
