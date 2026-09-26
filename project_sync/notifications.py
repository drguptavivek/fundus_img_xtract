"""Emails for the project data sync workflow.

Sent after the owning transaction commits. Delivery failures are logged by
``utils.emails``; they never roll back a grant state change.
"""
from __future__ import annotations

import logging

from flask import url_for

from utils.emails import send_email
from utils.log_sanitize import mask_email, sanitize_log_value

from .dto import GrantRequestResult, ProjectSyncGrantDTO

logger = logging.getLogger("project_sync")


def masked(email: str | None) -> str:
    return mask_email(email)


def _project_label(grant: ProjectSyncGrantDTO) -> str:
    return f"{grant.project_code} - {grant.project_title}"


def send_confirmation_email(result: GrantRequestResult) -> None:
    grant = result.grant
    link = url_for("project_sync_pages.confirm", token=result.email_token, _external=True)
    scope = "INCLUDING patient identifiers" if grant.include_pii else "de-identified (no patient identifiers)"
    body = (
        f"Hello {grant.username},\n\n"
        f"A request was made from your account to keep a local desktop copy of project "
        f"{_project_label(grant)} ({scope}).\n\n"
        f"Purpose given: {grant.purpose}\n\n"
        f"If you made this request, confirm it while signed in:\n{link}\n\n"
        "After you confirm, a system administrator must still approve the request before "
        "any data can be synchronised.\n\n"
        "If you did not make this request, ignore this email and tell your administrator."
    )
    send_email(result.recipient_email, "Confirm your project data sync request", body, sensitive=True)
    logger.info("project_sync confirmation email grant=%s to=%s",
                sanitize_log_value(grant.uuid), sanitize_log_value(mask_email(result.recipient_email)))


def notify_admins_pending(grant: ProjectSyncGrantDTO, admin_emails: list[str]) -> None:
    if not admin_emails:
        logger.warning("project_sync no admin email recipients for grant=%s", sanitize_log_value(grant.uuid))
        return
    link = url_for("project_sync_pages.admin", _external=True)
    body = (
        f"{grant.username} confirmed a request to keep a local copy of project {_project_label(grant)}.\n"
        f"Identifiers included: {'YES' if grant.include_pii else 'no'}\n"
        f"Purpose: {grant.purpose}\n\n"
        f"Review it here: {link}\n"
    )
    for email in admin_emails:
        send_email(email, "Project data sync request awaiting approval", body)


def notify_requester_decision(grant: ProjectSyncGrantDTO, email: str | None) -> None:
    if not email:
        return
    link = url_for("project_sync_pages.index", _external=True)
    if grant.status == "approved":
        body = (
            f"Your request to sync project {_project_label(grant)} was approved and is valid until "
            f"{grant.expires_at:%Y-%m-%d} (UTC).\n\n"
            f"Sign in and issue your desktop credential here: {link}\n"
        )
        subject = "Project data sync approved"
    else:
        body = (
            f"Your request to sync project {_project_label(grant)} was not approved.\n"
            f"Note: {grant.decision_note or '-'}\n"
        )
        subject = "Project data sync request declined"
    send_email(email, subject, body)


def notify_credential_issued(grant: ProjectSyncGrantDTO, email: str | None) -> None:
    if not email:
        return
    body = (
        f"A desktop sync credential ({grant.credential_prefix}...) was issued for project "
        f"{_project_label(grant)}. Any earlier credential for this grant has stopped working.\n\n"
        "If this was not you, revoke the grant immediately and contact your administrator."
    )
    send_email(email, "Project data sync credential issued", body)
