"""Audit trail for the field surface.

This surface lets a bearer-token client enumerate patients and spend money on
upstream inference and provider calls, so both reads and actions are recorded.
Reuses ``SensitiveOperationAudit`` rather than adding a parallel trail.
"""
from __future__ import annotations

import logging

from flask import request

from models import SensitiveOperationAudit
from utils.log_sanitize import sanitize_log_value

logger = logging.getLogger("field_workbench.audit")

OPERATION_QUEUE_READ = "field_encounter_queue_read"
OPERATION_DETAIL_READ = "field_encounter_detail_read"
OPERATION_INFERENCE_REQUEST = "field_inference_request"
OPERATION_FETCH_REQUEST = "field_upstream_fetch_request"


def record(
    db,
    *,
    user_id: int,
    operation_type: str,
    status: str = "completed",
    request_details: dict | None = None,
    result_details: dict | None = None,
) -> None:
    """Write one audit row. Never raises: auditing must not break the request.

    A failure here is logged rather than surfaced, because refusing a clinical
    read over an audit-write problem would be the worse outcome.
    """
    try:
        row = SensitiveOperationAudit(
            user_id=user_id,
            operation_type=operation_type,
            status=status,
            ip_address=request.remote_addr if request else None,
            user_agent=(request.headers.get("User-Agent") if request else None),
        )
        if request_details:
            row.set_request_details(request_details)
        if result_details:
            row.set_result_details(result_details)
        db.add(row)
        # Flush so the row participates in the caller's transaction rather
        # than depending on a later autoflush that may never happen on a
        # read-only request path.
        db.flush()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Field audit write failed: %s", sanitize_log_value(exc))
