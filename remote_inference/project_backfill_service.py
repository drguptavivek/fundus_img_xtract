"""Project-wide dispatch for configured EncounterSet WAI workflows."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select

from db_transaction_manager import transaction_scope
from job_store import db_create_job
from models import PatientEncounters, Project
from upload_profiles.admin_service import MutationResult
from utils.celery_helpers import enqueue_task


JOB_TYPE = "project_encounter_set_wai_backfill"
ITEM_KEY = "configured-wai-workflows"


def create_project_backfill_job(
    *, project_id: int, user: Any, remote_addr: str | None
) -> MutationResult:
    """Create one parent job; the worker discovers eligible project encounters."""
    with transaction_scope() as db:
        from authz.project_access import can_sync_remidio

        project = db.get(Project, project_id)
        if project is None:
            return MutationResult(False, "Project not found.", 404)
        if not can_sync_remidio(db, user, project_id=project_id):
            return MutationResult(
                False,
                "Project-wide WAI inference requires a project Data Manager grant.",
                403,
            )
        active = db.execute(
            select(PatientEncounters.id).where(
                PatientEncounters.project_id == project_id,
                PatientEncounters.is_set_based.is_(True),
            ).limit(1)
        ).first()
        if active is None:
            return MutationResult(False, "This project has no EncounterSets to process.", 409)

    token = db_create_job(
        [ITEM_KEY],
        [],
        uploader_user_id=user.id,
        uploader_username=user.username,
        uploader_ip=remote_addr,
        project_id=project_id,
        upload_type=JOB_TYPE,
        upload_kind="encounter_set",
    )
    try:
        enqueue_task(
            "celery_tasks.tasks.wadhwani_tasks.run_project_wai_backfill_task",
            token,
            project_id,
            user_id=user.id,
            username=user.username,
            remote_addr=remote_addr,
        )
    except Exception:
        from job_store import db_set_item_state, db_set_job_status

        db_set_item_state(token, ITEM_KEY, "error", "Could not enqueue project WAI dispatcher.")
        db_set_job_status(token, "error", error="Could not enqueue project WAI dispatcher.")
        return MutationResult(False, "Could not enqueue the project WAI job.", 503)
    return MutationResult(
        True,
        "Project WAI verification job created.",
        payload={"job_token": token, "project_id": project_id},
        status_code=202,
    )


def project_encounter_ids(project_id: int) -> list[int]:
    with transaction_scope() as db:
        return list(
            db.execute(
                select(PatientEncounters.id)
                .where(
                    PatientEncounters.project_id == project_id,
                    PatientEncounters.is_set_based.is_(True),
                )
                .order_by(PatientEncounters.id)
            ).scalars()
        )
