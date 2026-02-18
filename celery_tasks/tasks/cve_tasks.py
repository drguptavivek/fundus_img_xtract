"""
CVE Scanner Celery Tasks

Scheduled and on-demand vulnerability scanning using pip-audit.
"""

import os

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
    user_id: int | None = None,
    source_profile: str | None = None,
    expected_profile: str | None = None,
) -> dict:
    """
    Run CVE vulnerability scan and store results in database.

    Args:
        scan_type: "scheduled" (daily) or "on_demand" (manual trigger)
        user_id: User ID who triggered the scan (None for scheduled)
        source_profile: Source label persisted with scan result (e.g. general, ocr)
        expected_profile: Skip task if running worker profile does not match

    Returns:
        Dict with scan results including counts and any errors
    """
    from utils.cve_scanner import scan_vulnerabilities_and_save

    current_profile = (os.getenv("CELERY_TASKS_PROFILE", "unknown") or "unknown").strip().lower()
    if expected_profile and expected_profile.strip().lower() != current_profile:
        return {
            "status": "skipped",
            "reason": f"profile mismatch: expected={expected_profile}, current={current_profile}",
            "source_profile": current_profile,
            "total_count": 0,
        }

    with get_db_session() as db:
        return scan_vulnerabilities_and_save(
            db,
            scan_type=scan_type,
            triggered_by_user_id=user_id,
            source_profile=(source_profile or current_profile),
            use_cache=(scan_type != "on_demand"),
        )
