# job_store.py
import uuid
from datetime import datetime
from typing import List, Optional
from sqlalchemy.orm import Session as DBSession
from models import Session, Job, JobItem

def db_create_job(
    filenames: List[str],
    rejected: List[str],
    *,
    uploader_user_id: Optional[int] = None,
    uploader_username: Optional[str] = None,
    uploader_ip: Optional[str] = None,
) -> str:
    db: DBSession = Session()
    try:
        job = Job(
            token=uuid.uuid4().hex,
            status="queued",
            rejected_summary="; ".join(rejected) if rejected else None,
            uploader_user_id=uploader_user_id,
            uploader_username=uploader_username,
            uploader_ip=uploader_ip,
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
        db.commit()
        return job.token
    finally:
        db.close()

def db_set_job_status(job_token: str, status: str, error: str | None = None) -> None:
    db = Session()
    try:
        job = db.query(Job).filter_by(token=job_token).first()
        if not job:
            return
        job.status = status
        if error:
            job.error = error
        db.add(job)
        db.commit()
    finally:
        db.close()

def db_set_item_state(job_token: str, filename: str, state: str, detail: str | None = None) -> None:
    db = Session()
    try:
        job = db.query(Job).filter_by(token=job_token).first()
        if not job:
            return
        item = db.query(JobItem).filter_by(job_id=job.id, filename=filename).first()
        if not item:
            return
        now = datetime.utcnow()
        if state == "processing":
            item.started_at = now
        if state in ("ok", "error"):
            item.finished_at = now
        item.state = state
        if detail:
            item.detail = detail
        db.add(item)
        db.commit()
    finally:
        db.close()

def db_any_item_error(job_token: str) -> bool:
    db = Session()
    try:
        job = db.query(Job).filter_by(token=job_token).first()
        if not job:
            return True
        return any(it.state == "error" for it in job.items)
    finally:
        db.close()

def db_get_job_payload(job_token: str) -> dict | None:
    db = Session()
    try:
        job = db.query(Job).filter_by(token=job_token).first()
        if not job:
            return None
        return {
            "id": job.id,
            "token": job.token,
            "status": job.status,
            "error": job.error,
            "rejected_summary": job.rejected_summary,
            "uploader_user_id": job.uploader_user_id,
            "uploader_username": job.uploader_username,
            "uploader_ip": job.uploader_ip,
            "created_at": job.created_at.isoformat() + "Z" if job.created_at else None,
            "updated_at": job.updated_at.isoformat() + "Z" if job.updated_at else None,
            "items": [
                {
                    "id": it.id,
                    "filename": it.filename,
                    "state": it.state,
                    "detail": it.detail,
                    "uploader_user_id": it.uploader_user_id,
                    "uploader_username": it.uploader_username,
                    "uploader_ip": it.uploader_ip,
                    "started_at": it.started_at.isoformat() + "Z" if it.started_at else None,
                    "finished_at": it.finished_at.isoformat() + "Z" if it.finished_at else None,
                }
                for it in job.items
            ],
        }
    finally:
        db.close()
