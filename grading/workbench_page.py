"""Server-rendered transport for the normalized grading workbench DTO.

Two hosts render the same workbench body: the web page under ``/grading`` and
the grader PWA under ``/grader``. Every helper here takes the endpoint to land
on so the PWA can reuse acquisition, resume and rendering without copying them.
"""

from __future__ import annotations

from uuid import uuid4

from flask import flash, redirect, render_template, session as flask_session, url_for
from flask_login import current_user

from auth.roles import roles_required
from db_transaction_manager import transaction_scope
from grading.workbench.errors import ActiveSessionExists, WorkbenchError
from grading.workbench.browser_session import remember_session_token
from grading.workbench.service import (
    acquire_linked_followup_workbench,
    acquire_next_workbench,
    acquire_revision_workbench,
    acquire_package_workbench,
    acquire_task_workbench,
    load_workbench,
    resume_workbench,
)


WEB_WORKBENCH_ENDPOINT = "grading.workbench_page"
WEB_FALLBACK_ENDPOINT = "grading.index"


def register_routes(bp):
    bp.add_url_rule(
        "/workbench/<string:session_uuid>",
        view_func=workbench_page,
        methods=["GET"],
    )


def _open_workbench(
    acquire,
    *,
    workbench_endpoint: str,
    fallback_endpoint: str,
    no_work_category: str = "warning",
):
    """Lease a workbench (or resume the user's active one) and redirect into it.

    ``acquire`` receives the session and returns ``(workbench, token)``. An
    ``ActiveSessionExists`` carrying the active session's uuid resumes that
    session instead, so a grader who reopens a link lands back in their work.
    """
    try:
        with transaction_scope() as db:
            try:
                workbench, token = acquire(db)
            except ActiveSessionExists as exc:
                active_uuid = str(exc.details.get("session_uuid") or "")
                if not active_uuid:
                    raise
                workbench, token = resume_workbench(
                    db, session_uuid=active_uuid, user_id=current_user.id
                )
            remember_session_token(
                workbench.lease.session_uuid,
                token,
                workbench.lease.token_generation,
            )
        return redirect(
            url_for(workbench_endpoint, session_uuid=workbench.lease.session_uuid)
        )
    except WorkbenchError as exc:
        flash(str(exc), no_work_category)
        return redirect(url_for(fallback_endpoint))


def open_task_workbench(
    task_uuid: str,
    role_slot: str,
    *,
    workbench_endpoint: str = WEB_WORKBENCH_ENDPOINT,
    fallback_endpoint: str = WEB_FALLBACK_ENDPOINT,
):
    return _open_workbench(
        lambda db: acquire_task_workbench(
            db, user_id=current_user.id, task_uuid=task_uuid, role_slot=role_slot
        ),
        workbench_endpoint=workbench_endpoint,
        fallback_endpoint=fallback_endpoint,
    )


def open_revision_workbench(
    grade_id: int,
    *,
    workbench_endpoint: str = WEB_WORKBENCH_ENDPOINT,
    fallback_endpoint: str = WEB_FALLBACK_ENDPOINT,
):
    return _open_workbench(
        lambda db: acquire_revision_workbench(
            db, user_id=current_user.id, grade_id=grade_id
        ),
        workbench_endpoint=workbench_endpoint,
        fallback_endpoint=fallback_endpoint,
    )


def open_package_workbench(
    package_uuid: str,
    role_slot: str,
    *,
    workbench_endpoint: str = WEB_WORKBENCH_ENDPOINT,
    fallback_endpoint: str = WEB_FALLBACK_ENDPOINT,
):
    return _open_workbench(
        lambda db: acquire_package_workbench(
            db,
            user_id=current_user.id,
            package_uuid=package_uuid,
            role_slot=role_slot,
        ),
        workbench_endpoint=workbench_endpoint,
        fallback_endpoint=fallback_endpoint,
    )


def open_next_workbench(
    disease_id: int,
    role_slot: str,
    *,
    lab_unit_id: int | None = None,
    workbench_endpoint: str = WEB_WORKBENCH_ENDPOINT,
    fallback_endpoint: str = WEB_FALLBACK_ENDPOINT,
    no_work_category: str = "info",
):
    """Lease the next eligible case for a disease queue (the Start Grading path)."""
    return _open_workbench(
        lambda db: acquire_next_workbench(
            db,
            user_id=current_user.id,
            disease_id=disease_id,
            role_slot=role_slot,
            lab_unit_id=lab_unit_id,
        ),
        workbench_endpoint=workbench_endpoint,
        fallback_endpoint=fallback_endpoint,
        no_work_category=no_work_category,
    )


def open_linked_followup_workbench(
    primary_disease_id: int,
    linked_disease_id: int,
    *,
    workbench_endpoint: str = WEB_WORKBENCH_ENDPOINT,
    fallback_endpoint: str = WEB_FALLBACK_ENDPOINT,
    no_work_category: str = "info",
):
    return _open_workbench(
        lambda db: acquire_linked_followup_workbench(
            db,
            user_id=current_user.id,
            primary_disease_id=primary_disease_id,
            linked_disease_id=linked_disease_id,
        ),
        workbench_endpoint=workbench_endpoint,
        fallback_endpoint=fallback_endpoint,
        no_work_category=no_work_category,
    )


def render_workbench_page(
    session_uuid: str,
    *,
    template: str = "grading/workbench.html",
    fallback_endpoint: str = WEB_FALLBACK_ENDPOINT,
    **context,
):
    """Load (or resume) a session and render ``template`` with the workbench DTO.

    The browser-session token is reused when present so a reload never rotates
    the lease token; otherwise the session is resumed and the new token stored.
    Extra ``context`` lets a host override where the body's links go
    (``workbench_dashboard_url``, ``workbench_url_template``).
    """
    stored = flask_session.get(f"grading_workbench:{session_uuid}") or {}
    try:
        with transaction_scope() as db:
            if stored.get("token"):
                workbench = load_workbench(
                    db,
                    session_uuid=session_uuid,
                    user_id=current_user.id,
                    raw_token=stored["token"],
                    token_generation=int(stored.get("generation") or 0),
                )
                token = stored["token"]
            else:
                workbench, token = resume_workbench(
                    db, session_uuid=session_uuid, user_id=current_user.id
                )
                remember_session_token(
                    session_uuid, token, workbench.lease.token_generation
                )
        response = render_template(
            template,
            workbench=workbench.to_dict(),
            session_token=token,
            submission_idempotency_key=str(uuid4()),
            **context,
        )
        return response, 200, {"Cache-Control": "no-store, private"}
    except WorkbenchError as exc:
        flask_session.pop(f"grading_workbench:{session_uuid}", None)
        flash(str(exc), "warning")
        return redirect(url_for(fallback_endpoint))


@roles_required("ophthalmologist", "field_ophthalmologist")
def workbench_page(session_uuid: str):
    return render_workbench_page(session_uuid)
