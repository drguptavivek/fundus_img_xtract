"""Server-rendered transport for the normalized grading workbench DTO."""

from __future__ import annotations

from flask import flash, redirect, render_template, session as flask_session, url_for
from flask_login import current_user

from auth.roles import roles_required
from db_transaction_manager import transaction_scope
from grading.workbench.errors import ActiveSessionExists, WorkbenchError
from grading.workbench.service import (
    acquire_revision_workbench,
    acquire_package_workbench,
    acquire_task_workbench,
    load_workbench,
    resume_workbench,
)


def register_routes(bp):
    bp.add_url_rule(
        "/workbench/<string:session_uuid>",
        view_func=workbench_page,
        methods=["GET"],
    )


def remember_session_token(session_uuid: str, token: str, generation: int) -> None:
    flask_session[f"grading_workbench:{session_uuid}"] = {
        "token": token,
        "generation": generation,
    }


def open_task_workbench(task_uuid: str, role_slot: str):
    try:
        with transaction_scope() as db:
            try:
                workbench, token = acquire_task_workbench(
                    db,
                    user_id=current_user.id,
                    task_uuid=task_uuid,
                    role_slot=role_slot,
                )
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
            url_for("grading.workbench_page", session_uuid=workbench.lease.session_uuid)
        )
    except WorkbenchError as exc:
        flash(str(exc), "warning")
        return redirect(url_for("grading.index"))


def open_revision_workbench(grade_id: int):
    try:
        with transaction_scope() as db:
            try:
                workbench, token = acquire_revision_workbench(
                    db, user_id=current_user.id, grade_id=grade_id
                )
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
            url_for("grading.workbench_page", session_uuid=workbench.lease.session_uuid)
        )
    except WorkbenchError as exc:
        flash(str(exc), "warning")
        return redirect(url_for("grading.index"))


def open_package_workbench(package_uuid: str, role_slot: str):
    try:
        with transaction_scope() as db:
            try:
                workbench, token = acquire_package_workbench(
                    db,
                    user_id=current_user.id,
                    package_uuid=package_uuid,
                    role_slot=role_slot,
                )
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
            url_for("grading.workbench_page", session_uuid=workbench.lease.session_uuid)
        )
    except WorkbenchError as exc:
        flash(str(exc), "warning")
        return redirect(url_for("grading.index"))


@roles_required("resident", "ophthalmologist")
def workbench_page(session_uuid: str):
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
            "grading/workbench.html",
            workbench=workbench.to_dict(),
            session_token=token,
        )
        return response, 200, {"Cache-Control": "no-store, private"}
    except WorkbenchError as exc:
        flask_session.pop(f"grading_workbench:{session_uuid}", None)
        flash(str(exc), "warning")
        return redirect(url_for("grading.index"))
