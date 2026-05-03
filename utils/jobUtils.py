# utils/jobUtils.py
"""
Utility functions for handling job data, particularly for ZIP uploads
"""
from typing import List, Dict, Any
from sqlalchemy.orm import selectinload
from models import Job, LabUnit
from utils.utils import get_db_session


def get_recent_zip_uploads(
    limit: int = 100,
    job_type: str = "zip upload",
    include_null_types: bool = False,
    uploader_user_id: int | None = None,
) -> List[Dict[str, Any]]:
    """
    Get recent ZIP upload jobs with success/failure status

    Args:
        limit: Maximum number of records to return (default: 100)
        job_type: Type of job to filter (default: "zip upload")
        include_null_types: When True, include jobs where upload_type is NULL
            (useful for legacy rows that did not populate upload_type).
        uploader_user_id: When provided, restrict results to jobs created by
            this uploader.

    Returns:
        List of dictionaries containing job information and status counts
    """
    from db_transaction_manager import transaction_scope

    with transaction_scope() as db:
        # Query for jobs of specified type
        query = (
            db.query(Job)
            .options(selectinload(Job.lab_unit).selectinload(LabUnit.hospital))
            .options(selectinload(Job.items))
        )

        # Apply job type filter if provided
        if job_type:
            if include_null_types:
                query = query.filter(Job.upload_type.in_([job_type, None]))
            else:
                query = query.filter(Job.upload_type == job_type)
        if uploader_user_id is not None:
            query = query.filter(Job.uploader_user_id == uploader_user_id)

        jobs = (
            query
            .order_by(Job.created_at.desc())
            .limit(limit)
            .all()
        )

        # Get counts for each job
        result = []
        for job in jobs:
            # Count items by state
            total_items = len(job.items)
            successful_items = sum(1 for item in job.items if item.state in ("completed", "ok"))
            failed_items = sum(1 for item in job.items if item.state == "error")
            processing_items = sum(1 for item in job.items if item.state in ("queued", "processing"))
            
            # Determine overall status
            if processing_items > 0:
                status = "processing"
                status_class = "text-warning"
            elif failed_items > 0:
                status = "partial" if successful_items > 0 else "failed"
                status_class = "text-danger" if failed_items == total_items else "text-warning"
            else:
                status = "success"
                status_class = "text-success"
            
            # Extract essential job data to avoid session issues
            job_data = {
                'id': job.id,
                'token': job.token,
                'status': job.status,
                'upload_type': job.upload_type,
                'created_at': job.created_at,
                'updated_at': job.updated_at,
                'excel_filename': job.excel_filename,
                'uploader_username': job.uploader_username,
                'lab_unit': {
                    'id': job.lab_unit.id if job.lab_unit else None,
                    'name': job.lab_unit.name if job.lab_unit else None,
                    'hospital': {
                        'id': job.lab_unit.hospital.id if job.lab_unit and job.lab_unit.hospital else None,
                        'name': job.lab_unit.hospital.name if job.lab_unit and job.lab_unit.hospital else None
                    } if job.lab_unit and job.lab_unit.hospital else None
                } if job.lab_unit else None,
                'items': [
                    {
                        'id': item.id,
                        'filename': item.filename,
                        'state': item.state,
                        'started_at': item.started_at,
                        'finished_at': item.finished_at,
                        'detail': item.detail
                    }
                    for item in job.items
                ] if job.items else []
            }

            result.append({
                'job': job_data,  # Use extracted data instead of Job object
                'total_items': total_items,
                'successful_items': successful_items,
                'failed_items': failed_items,
                'processing_items': processing_items,
                'status': status,
                'status_class': status_class
            })
        
        return result
