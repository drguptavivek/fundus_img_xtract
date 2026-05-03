# job_store.py
import uuid
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy.orm import Session as DBSession, selectinload
from models import Job, JobItem, LabUnit
from db_transaction_manager import transaction_scope
from utils.log_sanitize import sanitize_log_value

def db_create_job(
    filenames: List[str],
    rejected: List[str],
    *,
    uploader_user_id: Optional[int] = None,
    uploader_username: Optional[str] = None,
    uploader_ip: Optional[str] = None,
    lab_unit_id: Optional[int] = None,
    project_id: Optional[int] = None,
    upload_type: Optional[str] = None,
    upload_kind: Optional[str] = None,
    upload_profile_id: Optional[int] = None,
) -> str:
    with transaction_scope() as db:
        job = Job(
            token=uuid.uuid4().hex,
            status="queued",
            rejected_summary="; ".join(rejected) if rejected else None,
            uploader_user_id=uploader_user_id,
            uploader_username=uploader_username,
            uploader_ip=uploader_ip,
            lab_unit_id=lab_unit_id,
            project_id=project_id,
            upload_type=upload_type,
            upload_kind=upload_kind,
            upload_profile_id=upload_profile_id,
        )
        db.add(job)
        db.flush()
        items = [
            JobItem(
                job_id=job.id,
                filename=fn,
                state="queued",
                uploader_user_id=uploader_user_id,
                uploader_username=uploader_username,
                uploader_ip=uploader_ip,
            )
            for fn in filenames
        ]
        db.add_all(items)
        return job.token

def db_set_job_status(job_token: str, status: str, error: str | None = None) -> None:
    with transaction_scope() as db:
        job = (
            db.query(Job)
            .options(selectinload(Job.lab_unit).selectinload(LabUnit.hospital))
            .options(selectinload(Job.project))
            .filter_by(token=job_token)
            .first()
        )
        if not job:
            return
        job.status = status
        if error:
            job.error = error
        db.add(job)

def db_set_item_state(job_token: str, filename: str, state: str, detail: str | None = None) -> None:
    with transaction_scope() as db:
        job = db.query(Job).filter_by(token=job_token).first()
        if not job:
            return
        item = db.query(JobItem).filter_by(job_id=job.id, filename=filename).first()
        if not item:
            return
        now = datetime.now(timezone.utc)
        if state == "processing":
            item.started_at = now
        if state in ("ok", "error"):
            item.finished_at = now
        item.state = state
        if detail:
            item.detail = detail
        db.add(item)

def db_any_item_error(job_token: str) -> bool:
    with transaction_scope() as db:
        job = db.query(Job).filter_by(token=job_token).first()
        if not job:
            return True
        return any(it.state == "error" for it in job.items)

def db_get_job_payload(job_token: str) -> dict | None:
    with transaction_scope() as db:
        job = db.query(Job).filter_by(token=job_token).first()
        if not job:
            return None
        is_export = job.upload_type in ("discrepancy_export", "dataset_export")
        
        return {
            "id": job.id,
            "token": job.token,
            "status": job.status,
            "error": job.error,
            "rejected_summary": sanitize_log_value(job.rejected_summary) if is_export else job.rejected_summary,
            "uploader_user_id": job.uploader_user_id,
            "uploader_username": sanitize_log_value(job.uploader_username),
            "uploader_ip": job.uploader_ip,
            "lab_unit_id": job.lab_unit_id,
            "lab_unit_name": job.lab_unit.name if getattr(job, "lab_unit", None) else None,
            "lab_unit_hospital_name": job.lab_unit.hospital.name if getattr(job, "lab_unit", None) and getattr(job.lab_unit, "hospital", None) else None,
            "project_id": job.project_id,
            "project_title": job.project.title if getattr(job, "project", None) else None,
            "project_code": job.project.code if getattr(job, "project", None) else None,
            "created_at": job.created_at.isoformat() + "Z" if job.created_at else None,
            "updated_at": job.updated_at.isoformat() + "Z" if job.updated_at else None,
            "items": [
                {
                    "id": it.id,
                    "filename": sanitize_log_value(it.filename) if is_export else it.filename,
                    "state": it.state,
                    "detail": sanitize_log_value(it.detail) if is_export else it.detail,
                    "uploader_user_id": it.uploader_user_id,
                    "uploader_username": sanitize_log_value(it.uploader_username),
                    "uploader_ip": it.uploader_ip,
                    "source_type": it.source_type,
                    "source_id": it.source_id,
                    "source_uuid": it.source_uuid,
                    "task_id": it.task_id,
                    "started_at": it.started_at.isoformat() + "Z" if it.started_at else None,
                    "finished_at": it.finished_at.isoformat() + "Z" if it.finished_at else None,
                }
                for it in job.items
            ],
        }
