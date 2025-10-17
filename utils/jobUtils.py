# utils/jobUtils.py
"""
Utility functions for handling job data, particularly for ZIP uploads
"""
from typing import List, Dict, Any
from sqlalchemy.orm import selectinload
from models import Session, Job, LabUnit


def get_recent_zip_uploads(limit: int = 100, job_type: str = "zip upload") -> List[Dict[str, Any]]:
    """
    Get recent ZIP upload jobs with success/failure status
    
    Args:
        limit: Maximum number of records to return (default: 100)
        job_type: Type of job to filter (default: "zip upload")
        
    Returns:
        List of dictionaries containing job information and status counts
    """
    db = Session()
    try:
        # Query for jobs of specified type
        query = (
            db.query(Job)
            .options(selectinload(Job.lab_unit).selectinload(LabUnit.hospital))
        )
        
        # Apply job type filter if provided
        if job_type:
            query = query.filter(Job.upload_type == job_type)
            
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
            successful_items = sum(1 for item in job.items if item.state == "completed")
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
            
            result.append({
                'job': job,
                'total_items': total_items,
                'successful_items': successful_items,
                'failed_items': failed_items,
                'processing_items': processing_items,
                'status': status,
                'status_class': status_class
            })
        
        return result
    finally:
        db.close()