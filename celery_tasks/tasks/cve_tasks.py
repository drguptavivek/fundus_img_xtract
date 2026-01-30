"""
CVE Scanner Celery Tasks

Scheduled and on-demand vulnerability scanning using pip-audit.
"""

from celery_app import celery_app
from db_transaction_manager import get_db_session


@celery_app.task(
    name="celery_tasks.tasks.cve_tasks.run_cve_scan_task",
    bind=True,
    acks_late=True
)
def run_cve_scan_task(
    self,
    scan_type: str = "scheduled",
    user_id: int | None = None
) -> dict:
    """
    Run CVE vulnerability scan and store results in database.

    Args:
        scan_type: "scheduled" (daily) or "on_demand" (manual trigger)
        user_id: User ID who triggered the scan (None for scheduled)

    Returns:
        Dict with scan results including counts and any errors
    """
    from utils.cve_scanner import scan_vulnerabilities_and_save
    from flask import current_app

    try:
        with get_db_session() as db:
            result = scan_vulnerabilities_and_save(
                db,
                scan_type=scan_type,
                triggered_by_user_id=user_id
            )
            current_app.logger.info(
                "CVE scan %s completed: %d vulnerabilities found",
                scan_type,
                result.get("total_count", 0)
            )
            return result
    except Exception as e:
        current_app.logger.error("CVE scan %s failed: %s", scan_type, e)
        return {
            "status": "error",
            "error": str(e),
            "total_count": 0
        }
