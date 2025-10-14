"""Utility functions for searching images across direct uploads and ZIP uploads.
 
This module provides centralized functions for searching images with various filters
and determining if they already have grading tasks for different diseases.
It supports both direct image uploads and images from ZIP uploads with proper
scoping based on user's lab units and role-based access controls.

Key Features:
- Strict filter separation (direct filters exclude ZIP images and vice versa)
- UUID-based returns (no original filenames)
- Task disease information for grading workflow
- Proper user lab unit scoping
- Comprehensive error handling and logging
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, Set
from datetime import datetime, date as _date
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session
from flask_login import current_user
import logging

from models import (
    DirectImageUpload,
    EncounterFile,
    PatientEncounters,
    User,
    LabUnit,
    Hospital,
    Camera,
    Disease,
    GradingTask as Task,
    Session as DBSession,
    Area,
    ZipFile,
    DiabeticRetinopathyReport,
    GlaucomaResultsCleaned
)
from utils.upload_eligibility import get_user_lab_unit_ids

# Configure logging
search_logger = logging.getLogger('image_search')


class ImageSearchError(Exception):
    """Custom exception for image search errors."""
    pass


def validate_search_filters(filters: Dict[str, Any], image_type: Optional[str] = None) -> str:
    """Validate all filters and determine search scope.
    
    Args:
        filters: Dictionary of search filters
        image_type: Explicit image type restriction ('direct', 'zip', or None)
        
    Returns:
        Search scope: 'direct_only', 'zip_only', or 'both'
        
    Raises:
        ImageSearchError: If filters are invalid or conflicting
    """
    # Check for conflicting filter types
    direct_filters_present = any([
        filters.get('camera_ids'),
        filters.get('disease_ids'),
        filters.get('area_ids'),
        filters.get('is_mydriatic') is not None
    ])
    
    zip_filters_present = any([
        filters.get('has_dr_report') is not None,
        filters.get('has_glaucoma_report') is not None,
        filters.get('capture_start'),
        filters.get('capture_end')
    ])
    
    # Enhanced conflict validation with image_type consideration
    if direct_filters_present and zip_filters_present:
        raise ImageSearchError(
            "Cannot apply both direct image filters and ZIP filters simultaneously. "
            "Direct filters: camera, disease, area, is_mydriatic. "
            "ZIP filters: has_dr_report, has_glaucoma_report, capture_date range."
        )
    
    # Check for conflicts between image_type and filter types
    if image_type == 'direct' and zip_filters_present:
        raise ImageSearchError(
            "Cannot apply ZIP-specific filters when searching direct images only. "
            "ZIP filters: has_dr_report, has_glaucoma_report, capture_date range. "
            "Direct images do not have DR or Glaucoma reports."
        )
    
    if image_type == 'zip' and direct_filters_present:
        raise ImageSearchError(
            "Cannot apply direct-specific filters when searching ZIP images only. "
            "Direct filters: camera, disease, area, is_mydriatic. "
            "ZIP images do not have these attributes."
        )
    
    # Date validation
    upload_start = filters.get('upload_start')
    upload_end = filters.get('upload_end')
    if upload_start and upload_end and upload_start > upload_end:
        raise ImageSearchError("upload_start date must be before upload_end date")
    
    capture_start = filters.get('capture_start')
    capture_end = filters.get('capture_end')
    if capture_start and capture_end and capture_start > capture_end:
        raise ImageSearchError("capture_start date must be before capture_end date")
    
    # Determine search scope
    if image_type == 'direct':
        return "direct_only"
    elif image_type == 'zip':
        return "zip_only"
    elif direct_filters_present:
        return "direct_only"
    elif zip_filters_present:
        return "zip_only"
    else:
        return "both"


def validate_pagination(page: int, per_page: int) -> Tuple[int, int]:
    """Validate and normalize pagination parameters.
    
    Args:
        page: Page number (1-indexed)
        per_page: Items per page
        
    Returns:
        Tuple of validated (page, per_page)
        
    Raises:
        ImageSearchError: If pagination parameters are invalid
    """
    if page < 1:
        raise ImageSearchError("Page must be >= 1")
    
    if per_page < 1:
        raise ImageSearchError("Per page must be >= 1")
    
    if per_page > 1000:  # Reasonable limit
        raise ImageSearchError("Per page cannot exceed 1000")
    
    return page, per_page


def get_user_search_scope(
    user_id: int,
    db_session: Session
) -> Tuple[Set[int], bool]:
    """Get user's lab unit IDs and admin status for search scoping.
    
    Args:
        user_id: User ID for scoping
        db_session: Database session
        
    Returns:
        Tuple of (lab_unit_ids, is_admin)
    """
    # Get user's lab units
    lab_unit_ids = get_user_lab_unit_ids(user_id)
    
    # Check if user is admin
    user = db_session.query(User).filter(User.id == user_id).first()
    is_admin = user.has_role('admin') if user else False
    
    return lab_unit_ids, is_admin


def build_direct_query(
    db_session: Session,
    filters: Dict[str, Any],
    user_lab_unit_ids: Set[int],
    is_admin: bool
):
    """Build query for direct images with all applicable filters.
    
    Args:
        db_session: Database session
        filters: Dictionary of filters to apply
        user_lab_unit_ids: Set of lab unit IDs user can access
        is_admin: Whether user is admin
        
    Returns:
        SQLAlchemy query object
    """
    from sqlalchemy.orm import joinedload
    
    query = db_session.query(DirectImageUpload).options(
        joinedload(DirectImageUpload.uploader)
    ).join(
        LabUnit, DirectImageUpload.lab_unit_id == LabUnit.id
    ).join(
        Hospital, DirectImageUpload.hospital_id == Hospital.id
    ).join(
        Camera, DirectImageUpload.camera_id == Camera.id
    ).join(
        Disease, DirectImageUpload.disease_id == Disease.id
    ).join(
        Area, DirectImageUpload.area_id == Area.id
    )
    
    # Apply user scoping
    if not is_admin and user_lab_unit_ids:
        query = query.filter(DirectImageUpload.lab_unit_id.in_(user_lab_unit_ids))
    
    # Apply global filters
    if filters.get('hospital_id'):
        query = query.filter(DirectImageUpload.hospital_id == filters['hospital_id'])
    
    if filters.get('lab_unit_ids'):
        query = query.filter(DirectImageUpload.lab_unit_id.in_(filters['lab_unit_ids']))
    
    # Apply date filters
    if filters.get('upload_start'):
        query = query.filter(DirectImageUpload.created_at >= filters['upload_start'])
    
    if filters.get('upload_end'):
        query = query.filter(DirectImageUpload.created_at <= filters['upload_end'])
    
    # Apply direct-specific filters
    if filters.get('camera_ids'):
        query = query.filter(DirectImageUpload.camera_id.in_(filters['camera_ids']))
    
    if filters.get('disease_ids'):
        query = query.filter(DirectImageUpload.disease_id.in_(filters['disease_ids']))
    
    if filters.get('area_ids'):
        query = query.filter(DirectImageUpload.area_id.in_(filters['area_ids']))
    
    if filters.get('is_mydriatic') is not None:
        query = query.filter(DirectImageUpload.is_mydriatic == filters['is_mydriatic'])
    
    # Apply search query
    if filters.get('search_query'):
        search_term = f"%{filters['search_query']}%"
        query = query.filter(
            or_(
                DirectImageUpload.uuid.like(search_term),
                DirectImageUpload.filename.like(search_term)
            )
        )
    
    return query


def build_zip_query(
    db_session: Session,
    filters: Dict[str, Any],
    user_lab_unit_ids: Set[int],
    is_admin: bool
):
    """Build query for ZIP images with all applicable filters.
    
    Args:
        db_session: Database session
        filters: Dictionary of filters to apply
        user_lab_unit_ids: Set of lab unit IDs user can access
        is_admin: Whether user is admin
        
    Returns:
        SQLAlchemy query object
    """
    query = db_session.query(EncounterFile).join(
        LabUnit, EncounterFile.lab_unit_id == LabUnit.id
    ).join(
        PatientEncounters, EncounterFile.patient_encounter_id == PatientEncounters.id
    ).join(
        ZipFile, PatientEncounters.zip_file_id == ZipFile.id
    ).join(
        Hospital, LabUnit.hospital_id == Hospital.id
    )
    
    # Apply user scoping
    if not is_admin and user_lab_unit_ids:
        query = query.filter(EncounterFile.lab_unit_id.in_(user_lab_unit_ids))
    
    # Apply global filters
    if filters.get('hospital_id'):
        query = query.filter(Hospital.id == filters['hospital_id'])
    
    if filters.get('lab_unit_ids'):
        query = query.filter(EncounterFile.lab_unit_id.in_(filters['lab_unit_ids']))
    
    # Apply upload date filters (from ZipFile)
    if filters.get('upload_start'):
        query = query.filter(ZipFile.upload_date >= filters['upload_start'])
    
    if filters.get('upload_end'):
        query = query.filter(ZipFile.upload_date <= filters['upload_end'])
    
    # Apply ZIP-specific filters
    if filters.get('capture_start'):
        query = query.filter(PatientEncounters.capture_date_dt >= filters['capture_start'])
    
    if filters.get('capture_end'):
        query = query.filter(PatientEncounters.capture_date_dt <= filters['capture_end'])
    
    # Apply DR report filter
    if filters.get('has_dr_report') is not None:
        if filters['has_dr_report']:
            query = query.join(
                DiabeticRetinopathyReport,
                PatientEncounters.id == DiabeticRetinopathyReport.patient_encounter_id
            ).filter(DiabeticRetinopathyReport.uuid.isnot(None))
        else:
            query = query.outerjoin(
                DiabeticRetinopathyReport,
                PatientEncounters.id == DiabeticRetinopathyReport.patient_encounter_id
            ).filter(
                or_(
                    DiabeticRetinopathyReport.id.is_(None),
                    DiabeticRetinopathyReport.uuid.is_(None)
                )
            )
    
    # Apply Glaucoma report filter
    if filters.get('has_glaucoma_report') is not None:
        if filters['has_glaucoma_report']:
            query = query.join(
                GlaucomaResultsCleaned,
                PatientEncounters.id == GlaucomaResultsCleaned.patient_encounter_id
            ).filter(GlaucomaResultsCleaned.report_uuid.isnot(None))
        else:
            query = query.outerjoin(
                GlaucomaResultsCleaned,
                PatientEncounters.id == GlaucomaResultsCleaned.patient_encounter_id
            ).filter(
                or_(
                    GlaucomaResultsCleaned.id.is_(None),
                    GlaucomaResultsCleaned.report_uuid.is_(None)
                )
            )
    
    # Apply search query
    if filters.get('search_query'):
        search_term = f"%{filters['search_query']}%"
        query = query.filter(
            or_(
                EncounterFile.uuid.like(search_term),
                EncounterFile.filename.like(search_term),
                PatientEncounters.patient_id.like(search_term),
                PatientEncounters.name.like(search_term)
            )
        )
    
    return query


def get_tasks_for_multiple_images(
    db_session: Session,
    image_ids: List[int],
    image_type: str
) -> Dict[int, List[str]]:
    """Get task diseases for multiple images efficiently.
    
    Args:
        db_session: Database session
        image_ids: List of image IDs
        image_type: Type of image ('direct' or 'zip')
        
    Returns:
        Dictionary mapping image_id to list of disease names with tasks
    """
    if not image_ids:
        return {}
    
    tasks = db_session.query(Task, Disease).join(Disease).filter(
        Task.state.in_(['pending', 'resident_done', 'faculty_done', 'arbitration', 'final'])
    )
    
    if image_type == "direct":
        tasks = tasks.filter(Task.direct_image_upload_id.in_(image_ids))
    else:  # zip
        tasks = tasks.filter(Task.encounter_file_id.in_(image_ids))
    
    # Group by image ID
    result = {}
    for task, disease in tasks.all():
        image_id = task.direct_image_upload_id if image_type == "direct" else task.encounter_file_id
        if image_id not in result:
            result[image_id] = []
        result[image_id].append(disease.name)
    
    return result


def format_direct_image_with_tasks(
    item: DirectImageUpload,
    task_diseases: List[str]
) -> Dict[str, Any]:
    """Format direct image with pre-fetched task information.
    
    Args:
        item: DirectImageUpload object
        task_diseases: List of disease names with tasks for this image
        
    Returns:
        Formatted image dictionary
    """
    return {
        "uuid": item.uuid,
        "type": "direct",
        "upload_date": item.created_at,
        "capture_date": item.created_at,  # Same as upload_date for direct images
        "hospital": item.hospital.name if item.hospital else None,
        "lab_unit": item.lab_unit.name if item.lab_unit else None,
        "camera": item.camera.name if item.camera else None,
        "disease": item.disease.name if item.disease else None,
        "area": item.area.name if item.area else None,
        "is_mydriatic": item.is_mydriatic,
        "tasks_for_diseases": task_diseases,
        "uploader": item.uploader.username if item.uploader else None,
        "file_hash": getattr(item, 'file_hash', None),
    }


def format_zip_image_with_tasks(
    item: EncounterFile,
    task_diseases: List[str],
    db_session: Session
) -> Dict[str, Any]:
    """Format ZIP image with pre-fetched task information.
    
    Args:
        item: EncounterFile object
        task_diseases: List of disease names with tasks for this image
        db_session: Database session
        
    Returns:
        Formatted image dictionary
    """
    # Get report status (still need to query individually for this)
    has_dr_report = db_session.query(DiabeticRetinopathyReport).filter(
        DiabeticRetinopathyReport.patient_encounter_id == item.patient_encounter.id,
        DiabeticRetinopathyReport.uuid.isnot(None)
    ).first() is not None
    
    has_glaucoma_report = db_session.query(GlaucomaResultsCleaned).filter(
        GlaucomaResultsCleaned.patient_encounter_id == item.patient_encounter.id,
        GlaucomaResultsCleaned.report_uuid.isnot(None)
    ).first() is not None
    
    return {
        "uuid": item.uuid,
        "type": "zip",
        "upload_date": item.patient_encounter.zip_file.upload_date,
        "capture_date": item.patient_encounter.capture_date_dt,
        "hospital": item.lab_unit.hospital.name if item.lab_unit and item.lab_unit.hospital else None,
        "lab_unit": item.lab_unit.name if item.lab_unit else None,
        "has_dr_report": has_dr_report,
        "has_glaucoma_report": has_glaucoma_report,
        "tasks_for_diseases": task_diseases,
    }


def log_search_request(
    user_id: int,
    filters: Dict[str, Any],
    search_scope: str,
    page: int,
    per_page: int
) -> None:
    """Log search request for debugging and audit.
    
    Args:
        user_id: User ID making the request
        filters: Applied filters
        search_scope: Determined search scope
        page: Page number
        per_page: Items per page
    """
    search_logger.info(
        f"Image search request - User: {user_id}, Scope: {search_scope}, "
        f"Page: {page}, Per_page: {per_page}, Filters: {filters}"
    )


def log_search_results(
    user_id: int,
    search_scope: str,
    total_count: int,
    execution_time: float
) -> None:
    """Log search results for performance monitoring.
    
    Args:
        user_id: User ID making the request
        search_scope: Search scope used
        total_count: Total results found
        execution_time: Query execution time in seconds
    """
    search_logger.info(
        f"Search completed - User: {user_id}, Scope: {search_scope}, "
        f"Total: {total_count}, Time: {execution_time:.3f}s"
    )


def log_search_error(user_id: int, error: Exception, filters: Dict[str, Any]) -> None:
    """Log search errors for debugging.
    
    Args:
        user_id: User ID making the request
        error: Exception that occurred
        filters: Filters that were applied
    """
    search_logger.error(
        f"Search error - User: {user_id}, Error: {str(error)}, "
        f"Filters: {filters}", exc_info=True
    )


def search_images_strict(
    db_session: Session,
    page: int = 1,
    per_page: int = 50,
    hospital_id: Optional[int] = None,
    lab_unit_ids: Optional[List[int]] = None,
    upload_start: Optional[_date] = None,
    upload_end: Optional[_date] = None,
    # Direct image filters
    camera_ids: Optional[List[int]] = None,
    disease_ids: Optional[List[int]] = None,
    area_ids: Optional[List[int]] = None,
    is_mydriatic: Optional[bool] = None,
    # ZIP image filters
    has_dr_report: Optional[bool] = None,
    has_glaucoma_report: Optional[bool] = None,
    capture_start: Optional[_date] = None,
    capture_end: Optional[_date] = None,
    # Additional options
    search_query: Optional[str] = None,
    user_id: Optional[int] = None,  # For scoping, defaults to current_user
    image_type: Optional[str] = None  # 'direct', 'zip', or None for both
) -> Tuple[List[Dict[str, Any]], int]:
    """Search images with strict filter separation and UUID-based returns.
    
    This function implements strict filter separation:
    - Direct filters (camera, disease, area, is_mydriatic) exclude ZIP images
    - ZIP filters (has_dr_report, has_glaucoma_report, capture_date) exclude Direct images
    - Global filters (hospital, lab_unit, upload dates) apply to both when no specific filters
    
    Args:
        db_session: Database session to use for queries
        page: Page number for pagination (1-indexed), default is 1
        per_page: Number of items per page, default is 50
        hospital_id: Hospital ID to filter by (global filter)
        lab_unit_ids: List of lab unit IDs to filter by (global filter)
        upload_start: Filter for upload date start (global filter)
        upload_end: Filter for upload date end (global filter)
        camera_ids: List of camera IDs to filter by (direct filter)
        disease_ids: List of disease IDs to filter by (direct filter)
        area_ids: List of area IDs to filter by (direct filter)
        is_mydriatic: Filter for mydriatic status (direct filter)
        has_dr_report: Filter for DR report status (ZIP filter)
        has_glaucoma_report: Filter for Glaucoma report status (ZIP filter)
        capture_start: Filter for capture date start (ZIP filter)
        capture_end: Filter for capture date end (ZIP filter)
        search_query: Search term to match against UUIDs and other fields
        user_id: User ID for scoping (defaults to current_user)
    
    Returns:
        Tuple of (list of image dictionaries, total count)
        
    Raises:
        ImageSearchError: If filters are invalid or conflicting
    """
    start_time = datetime.now()
    
    # Prepare filters dictionary early for error logging
    filters = {
        'hospital_id': hospital_id,
        'lab_unit_ids': lab_unit_ids,
        'upload_start': upload_start,
        'upload_end': upload_end,
        'camera_ids': camera_ids,
        'disease_ids': disease_ids,
        'area_ids': area_ids,
        'is_mydriatic': is_mydriatic,
        'has_dr_report': has_dr_report,
        'has_glaucoma_report': has_glaucoma_report,
        'capture_start': capture_start,
        'capture_end': capture_end,
        'search_query': search_query
    }
    
    try:
        # Validate pagination
        page, per_page = validate_pagination(page, per_page)
        
        # Get user ID for scoping
        if user_id is None:
            try:
                if current_user and current_user.is_authenticated:
                    user_id = current_user.id
                else:
                    raise ImageSearchError("User ID required for search")
            except AttributeError:
                # current_user is not available (e.g., in testing)
                raise ImageSearchError("User ID required for search")
        
        # Validate filters and determine search scope
        search_scope = validate_search_filters(filters, image_type)
        
        # Override search scope based on explicit image_type parameter
        if image_type == 'direct':
            search_scope = 'direct_only'
        elif image_type == 'zip':
            search_scope = 'zip_only'
        # If image_type is None or 'all', keep the determined search_scope
        
        # Get user scoping information
        user_lab_unit_ids, is_admin = get_user_search_scope(user_id, db_session)
        
        # Log search request
        log_search_request(user_id, filters, search_scope, page, per_page)
        
        # Calculate offset
        offset = (page - 1) * per_page
        
        # Execute queries based on search scope
        all_results = []
        total_count = 0
        
        if search_scope in ['direct_only', 'both']:
            # Build and execute direct image query
            direct_query = build_direct_query(db_session, filters, user_lab_unit_ids, is_admin)
            direct_count = direct_query.count()
            total_count += direct_count
            
            if direct_count > 0:
                # Get all results (no pagination yet)
                direct_results = direct_query.order_by(
                    DirectImageUpload.created_at.desc()
                ).all()
                
                # Get task information for direct images
                direct_image_ids = [img.id for img in direct_results]
                direct_tasks = get_tasks_for_multiple_images(db_session, direct_image_ids, 'direct')
                
                # Format results
                for img in direct_results:
                    formatted = format_direct_image_with_tasks(img, direct_tasks.get(img.id, []))
                    all_results.append(formatted)
        
        if search_scope in ['zip_only', 'both']:
            # Build and execute ZIP image query
            zip_query = build_zip_query(db_session, filters, user_lab_unit_ids, is_admin)
            zip_count = zip_query.count()
            total_count += zip_count
            
            if zip_count > 0:
                # Get all results (no pagination yet)
                zip_results = zip_query.order_by(
                    ZipFile.upload_date.desc().nulls_last()
                ).all()
                
                # Get task information for ZIP images
                zip_image_ids = [img.id for img in zip_results]
                zip_tasks = get_tasks_for_multiple_images(db_session, zip_image_ids, 'zip')
                
                # Format results
                for img in zip_results:
                    formatted = format_zip_image_with_tasks(img, zip_tasks.get(img.id, []), db_session)
                    all_results.append(formatted)
        
        # Sort combined results by upload_date (most recent first)
        # Handle both datetime and date objects safely
        def sort_key(item):
            upload_date = item.get('upload_date')
            if upload_date is None:
                return ''
            # Convert date to datetime for consistent comparison
            if hasattr(upload_date, 'date'):  # It's a datetime
                return upload_date
            else:  # It's a date, convert to datetime
                from datetime import datetime, time
                return datetime.combine(upload_date, time.min)
        
        all_results.sort(key=sort_key, reverse=True)
        
        # Apply pagination to combined results
        start_idx = offset
        end_idx = offset + per_page
        paginated_results = all_results[start_idx:end_idx]
        
        # Log successful completion
        execution_time = (datetime.now() - start_time).total_seconds()
        log_search_results(user_id, search_scope, total_count, execution_time)
        
        return paginated_results, total_count
        
    except Exception as e:
        # Log error
        execution_time = (datetime.now() - start_time).total_seconds()
        log_search_error(user_id or 0, e, filters)
        
        # Re-raise as ImageSearchError if not already
        if not isinstance(e, ImageSearchError):
            raise ImageSearchError(f"Search failed: {str(e)}") from e
        raise


__all__ = [
    'search_images_strict',
    'ImageSearchError'
]