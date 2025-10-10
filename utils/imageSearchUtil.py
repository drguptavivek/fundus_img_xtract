"""Utility functions for searching images across direct uploads and ZIP uploads.

This module provides centralized functions for searching images with various filters
and determining if they already have grading tasks for different diseases.
It supports both direct image uploads and images from ZIP uploads with proper
scoping based on user's lab units and role-based access controls.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session
from flask_login import current_user

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
    Area
)
from utils.upload_eligibility import get_user_lab_unit_ids


def search_images(
    db_session,
    page: int = 1,
    per_page: int = 50,
    lab_unit_ids: Optional[List[int]] = None,
    disease_ids: Optional[List[int]] = None,
    camera_ids: Optional[List[int]] = None,
    area_ids: Optional[List[int]] = None,
    is_mydriatic: Optional[bool] = None,
    has_task_for_diseases: Optional[List[int]] = None,
    exclude_task_for_diseases: Optional[List[int]] = None,
    image_type: Optional[str] = None,  # 'direct' or 'zip'
    search_query: Optional[str] = None
) -> Tuple[List[Dict[str, Any]], int]:
    """Search images across both direct uploads and ZIP uploads with specified filters.
    
    Args:
        db_session: Database session to use for queries
        page: Page number for pagination (1-indexed), default is 1
        per_page: Number of items per page, default is 50
        lab_unit_ids: List of lab unit IDs to filter by
        disease_ids: List of disease IDs to filter by
        camera_ids: List of camera IDs to filter by
        area_ids: List of area IDs to filter by
        is_mydriatic: Filter for mydriatic status (True for mydriatic, False for non-mydriatic)
        has_task_for_diseases: List of disease IDs to check if tasks exist for
        exclude_task_for_diseases: List of disease IDs to exclude if tasks exist for
        image_type: Filter for image type ('direct' or 'zip'), None for both
        search_query: Search term to match against patient IDs, filenames, etc.
    
    Returns:
        Tuple of (list of image dictionaries, total count)
    """
    from sqlalchemy import union_all, text
    from sqlalchemy.sql import select
    
    # Get user's lab units if not explicitly provided and not admin
    if not (current_user.has_role('admin') if current_user.is_authenticated else False):
        if lab_unit_ids is None:
            lab_unit_ids = get_user_lab_unit_ids(current_user.id)
    
    offset = (page - 1) * per_page
    
    # Subquery for direct uploads
    if image_type in [None, 'direct']:
        direct_subq = select(
            DirectImageUpload.id,
            DirectImageUpload.uuid,
            DirectImageUpload.filename,
            (DirectImageUpload.folder_rel + '/' + DirectImageUpload.filename).label('file_path'),
            LabUnit.name.label('lab_unit_name'),
            Hospital.name.label('hospital_name'),
            Camera.name.label('camera_name'),
            Disease.name.label('disease_name'),
            Area.name.label('area_name'),
            DirectImageUpload.is_mydriatic,
            DirectImageUpload.created_at,
            text("'direct'").label('image_type')
        ).select_from(
            DirectImageUpload.__table__
            .join(LabUnit, DirectImageUpload.lab_unit_id == LabUnit.id)
            .join(Hospital, DirectImageUpload.hospital_id == Hospital.id)
            .join(Camera, DirectImageUpload.camera_id == Camera.id)
            .join(Disease, DirectImageUpload.disease_id == Disease.id)
            .join(Area, DirectImageUpload.area_id == Area.id)
        ).where(DirectImageUpload.id > 0)
        
        # Apply filters for direct uploads
        if lab_unit_ids:
            direct_subq = direct_subq.where(DirectImageUpload.lab_unit_id.in_(lab_unit_ids))
        if disease_ids:
            direct_subq = direct_subq.where(DirectImageUpload.disease_id.in_(disease_ids))
        if camera_ids:
            direct_subq = direct_subq.where(DirectImageUpload.camera_id.in_(camera_ids))
        if area_ids:
            direct_subq = direct_subq.where(DirectImageUpload.area_id.in_(area_ids))
        if is_mydriatic is not None:
            direct_subq = direct_subq.where(DirectImageUpload.is_mydriatic == is_mydriatic)
        if search_query:
            direct_subq = direct_subq.where(
                or_(
                    DirectImageUpload.filename.contains(search_query),
                    DirectImageUpload.uuid.contains(search_query),
                    DirectImageUpload.folder_rel.contains(search_query)
                )
            )
    else:
        direct_subq = None
    
    # Subquery for ZIP uploads (EncounterFile)
    if image_type in [None, 'zip']:
        zip_subq = select(
            EncounterFile.id,
            EncounterFile.uuid,
            EncounterFile.filename,
            EncounterFile.filename.label('file_path'),  # ZIP files don't have folder_rel
            LabUnit.name.label('lab_unit_name'),
            text("NULL").label('hospital_name'),  # ZIP files don't have the same structure
            text("NULL").label('camera_name'),
            text("NULL").label('disease_name'),
            text("NULL").label('area_name'),
            text("NULL").label('is_mydriatic'),  # ZIP files don't have this field in the same way
            EncounterFile.created_at,
            text("'zip'").label('image_type')
        ).select_from(
            EncounterFile.__table__
            .join(LabUnit, EncounterFile.lab_unit_id == LabUnit.id)
            .join(PatientEncounters, EncounterFile.patient_encounter_id == PatientEncounters.id)
        ).where(EncounterFile.id > 0)
        
        # Apply filters for ZIP uploads
        if lab_unit_ids:
            zip_subq = zip_subq.where(EncounterFile.lab_unit_id.in_(lab_unit_ids))
        if search_query:
            zip_subq = zip_subq.where(
                or_(
                    EncounterFile.filename.contains(search_query),
                    EncounterFile.uuid.contains(search_query),
                    PatientEncounters.patient_id.contains(search_query),
                    PatientEncounters.name.contains(search_query)
                )
            )
    else:
        zip_subq = None
    
    # Create the union query
    if direct_subq is not None and zip_subq is not None:
        combined_query = union_all(direct_subq, zip_subq).alias('combined_results')
    elif direct_subq is not None:
        combined_query = direct_subq.alias('combined_results')
    elif zip_subq is not None:
        combined_query = zip_subq.alias('combined_results')
    else:
        return [], 0

    # Count total records
    count_query = select(combined_query.c.id).select_from(combined_query)
    total_count = db_session.execute(count_query).fetchall()
    total_count = len(total_count)
    
    # Main query with pagination
    paginated_query = select(combined_query).select_from(combined_query).order_by(
        combined_query.c.created_at.desc()
    ).offset(offset).limit(per_page)
    
    paginated_results = db_session.execute(paginated_query).fetchall()
    
    # Format the results
    images = []
    for result in paginated_results:
        image_dict = {
            'id': result.id,
            'uuid': result.uuid,
            'filename': result.filename,
            'file_path': result.file_path,
            'lab_unit': result.lab_unit_name,
            'created_at': result.created_at,
            'type': result.image_type
        }
        
        # Add type-specific fields
        if result.image_type == 'direct':
            image_dict['hospital'] = result.hospital_name
            image_dict['camera'] = result.camera_name
            image_dict['disease'] = result.disease_name
            image_dict['area'] = result.area_name
            image_dict['is_mydriatic'] = result.is_mydriatic
        elif result.image_type == 'zip':
            # Add patient info for ZIP files
            pass
        
        # Check task status for this image
        image_dict['has_tasks'] = get_image_task_status(db_session, result.id, result.image_type)
        
        images.append(image_dict)
    
    return images, total_count


def search_direct_images(
    db_session,
    page: int = 1,
    per_page: int = 50,
    lab_unit_ids: Optional[List[int]] = None,
    disease_ids: Optional[List[int]] = None,
    camera_ids: Optional[List[int]] = None,
    area_ids: Optional[List[int]] = None,
    is_mydriatic: Optional[bool] = None,
    has_task_for_diseases: Optional[List[int]] = None,
    exclude_task_for_diseases: Optional[List[int]] = None,
    search_query: Optional[str] = None
) -> Tuple[List[Dict[str, Any]], int]:
    """Search direct image uploads with specified filters.
    
    Args:
        db_session: Database session to use for queries
        page: Page number for pagination (1-indexed), default is 1
        per_page: Number of items per page, default is 50
        lab_unit_ids: List of lab unit IDs to filter by
        disease_ids: List of disease IDs to filter by
        camera_ids: List of camera IDs to filter by
        area_ids: List of area IDs to filter by
        is_mydriatic: Filter for mydriatic status (True for mydriatic, False for non-mydriatic)
        has_task_for_diseases: List of disease IDs to check if tasks exist for
        exclude_task_for_diseases: List of disease IDs to exclude if tasks exist for
        search_query: Search term to match against patient IDs, filenames, etc.
    
    Returns:
        Tuple of (list of image dictionaries, total count)
    """
    offset = (page - 1) * per_page
    
    # Get user's lab units if not explicitly provided
    if not (current_user.has_role('admin') if current_user.is_authenticated else False):
        if lab_unit_ids is None:
            lab_unit_ids = get_user_lab_unit_ids(current_user.id)
    
    # Base query for direct uploads
    query = db_session.query(DirectImageUpload).join(LabUnit).join(Hospital).join(Camera).join(Disease).join(Area)
    
    # Apply filters
    if lab_unit_ids:
        query = query.filter(DirectImageUpload.lab_unit_id.in_(lab_unit_ids))
    if disease_ids:
        query = query.filter(DirectImageUpload.disease_id.in_(disease_ids))
    if camera_ids:
        query = query.filter(DirectImageUpload.camera_id.in_(camera_ids))
    if area_ids:
        query = query.filter(DirectImageUpload.area_id.in_(area_ids))
    if is_mydriatic is not None:
        query = query.filter(DirectImageUpload.is_mydriatic == is_mydriatic)
    if search_query:
        query = query.filter(
            or_(
                DirectImageUpload.filename.contains(search_query),
                DirectImageUpload.uuid.contains(search_query),
                DirectImageUpload.folder_rel.contains(search_query)
            )
        )
    
    # Count total results
    total_count = query.count()
    
    # Apply ordering and pagination
    uploads = query.order_by(DirectImageUpload.created_at.desc()).offset(offset).limit(per_page).all()
    
    # Format results
    image_list = [format_direct_image_upload(db_session, upload, has_task_for_diseases, exclude_task_for_diseases) for upload in uploads]
    
    return image_list, total_count


def search_zip_images(
    db_session,
    page: int = 1,
    per_page: int = 50,
    lab_unit_ids: Optional[List[int]] = None,
    search_query: Optional[str] = None
) -> Tuple[List[Dict[str, Any]], int]:
    """Search images from ZIP uploads with specified filters.
    
    Args:
        db_session: Database session to use for queries
        page: Page number for pagination (1-indexed), default is 1
        per_page: Number of items per page, default is 50
        lab_unit_ids: List of lab unit IDs to filter by
        search_query: Search term to match against patient IDs, filenames, etc.
    
    Returns:
        Tuple of (list of image dictionaries, total count)
    """
    offset = (page - 1) * per_page
    
    # Get user's lab units if not explicitly provided
    if not (current_user.has_role('admin') if current_user.is_authenticated else False):
        if lab_unit_ids is None:
            lab_unit_ids = get_user_lab_unit_ids(current_user.id)
    
    # Base query for ZIP uploads (EncounterFile)
    query = db_session.query(EncounterFile).join(LabUnit).join(PatientEncounters)
    
    # Apply filters
    if lab_unit_ids:
        query = query.filter(EncounterFile.lab_unit_id.in_(lab_unit_ids))
    if search_query:
        query = query.filter(
            or_(
                EncounterFile.filename.contains(search_query),
                EncounterFile.uuid.contains(search_query),
                PatientEncounters.patient_id.contains(search_query),
                PatientEncounters.name.contains(search_query)
            )
        )
    
    # Count total results
    total_count = query.count()
    
    # Apply ordering and pagination
    uploads = query.order_by(EncounterFile.created_at.desc()).offset(offset).limit(per_page).all()
    
    # Format results
    image_list = [format_encounter_file(db_session, upload) for upload in uploads]
    
    return image_list, total_count


def format_direct_image_upload(db_session, upload, has_task_for_diseases=None, exclude_task_for_diseases=None):
    """Format a direct image upload for return in search results.
    
    Args:
        db_session: Database session to use for queries
        upload: DirectImageUpload object to format
        has_task_for_diseases: List of disease IDs to check if tasks exist for
        exclude_task_for_diseases: List of disease IDs to exclude if tasks exist for
    
    Returns:
        Dictionary representation of the upload or None if filtered out
    """
    # Check if tasks exist for specific diseases
    has_tasks = {}
    all_diseases = db_session.query(Disease).all()
    
    for disease in all_diseases:
        task_exists = db_session.query(Task).filter(
            Task.direct_image_upload_id == upload.id,
            Task.disease_id == disease.id
        ).count() > 0
        
        has_tasks[disease.name] = task_exists
    
    # Filter based on requirements
    if has_task_for_diseases:
        # Only include if has tasks for ALL specified diseases
        has_all_required_tasks = all(has_tasks.get(disease.name, False) for disease in all_diseases if disease.id in has_task_for_diseases)
        if not has_all_required_tasks:
            return None  # Skip this image
    
    if exclude_task_for_diseases:
        # Exclude if has tasks for ANY of the specified diseases
        has_any_excluded_task = any(has_tasks.get(disease.name, False) for disease in all_diseases if disease.id in exclude_task_for_diseases)
        if has_any_excluded_task:
            return None  # Skip this image
    
    return {
        'id': upload.id,
        'uuid': upload.uuid,
        'type': 'direct',
        'filename': upload.filename,
        'file_path': f"{upload.folder_rel}/{upload.filename}",
        'lab_unit': upload.lab_unit.name,
        'hospital': upload.hospital.name,
        'camera': upload.camera.name,
        'disease': upload.disease.name,
        'area': upload.area.name,
        'is_mydriatic': upload.is_mydriatic,
        'created_at': upload.created_at,
        'has_tasks': has_tasks,
        # Add more fields as needed
    }


def format_encounter_file(db_session, file):
    """Format an encounter file (from ZIP) for return in search results.
    
    Args:
        db_session: Database session to use for queries
        file: EncounterFile object to format
    
    Returns:
        Dictionary representation of the file
    """
    # Check if tasks exist for this image (encounter_file_id)
    has_tasks = {}
    all_diseases = db_session.query(Disease).all()
    
    for disease in all_diseases:
        task_exists = db_session.query(Task).filter(
            Task.encounter_file_id == file.id,
            Task.disease_id == disease.id
        ).count() > 0
        
        has_tasks[disease.name] = task_exists
    
    return {
        'id': file.id,
        'uuid': file.uuid,
        'type': 'zip',
        'filename': file.filename,
        'lab_unit': file.lab_unit.name,
        'patient_id': getattr(file.patient_encounter, 'patient_id', 'Unknown'),
        'patient_name': getattr(file.patient_encounter, 'name', 'Unknown'),
        'created_at': getattr(file.patient_encounter, 'capture_date_dt', None) or getattr(file.patient_encounter, 'capture_date', None),
        'has_tasks': has_tasks,
        # Add more fields as needed
    }


def get_image_task_status(db_session, image_id: int, image_type: str) -> Dict[str, bool]:
    """Get task status for all diseases for a specific image.
    
    Args:
        db_session: Database session to use for queries
        image_id: ID of the image
        image_type: Type of image ('direct' or 'zip')
    
    Returns:
        Dictionary mapping disease names to whether a task exists for that disease
    """
    has_tasks = {}
    all_diseases = db_session.query(Disease).all()
    
    for disease in all_diseases:
        if image_type == 'direct':
            task_exists = db_session.query(Task).filter(
                Task.direct_image_upload_id == image_id,
                Task.disease_id == disease.id
            ).count() > 0
        elif image_type == 'zip':
            task_exists = db_session.query(Task).filter(
                Task.encounter_file_id == image_id,
                Task.disease_id == disease.id
            ).count() > 0
        else:
            task_exists = False
        
        has_tasks[disease.name] = task_exists
    
    return has_tasks


def bulk_create_tasks(
    db_session,
    image_ids: List[int],
    image_type: str,
    disease_ids: List[int],
    lab_unit_id: int
) -> Dict[str, Any]:
    """Create grading tasks for specified images and diseases.
    
    Args:
        db_session: Database session to use for queries
        image_ids: List of image IDs to create tasks for
        image_type: Type of image ('direct' or 'zip')
        disease_ids: List of disease IDs to create tasks for
        lab_unit_id: Lab unit ID to associate with the tasks
    
    Returns:
        Dictionary with summary of created tasks
    """
    created_tasks = []
    skipped_tasks = []  # For images that already have tasks for specified diseases
    
    for image_id in image_ids:
        for disease_id in disease_ids:
            # Check if a task already exists for this image-disease combination
            existing_task = None
            if image_type == 'direct':
                existing_task = db_session.query(Task).filter(
                    Task.direct_image_upload_id == image_id,
                    Task.disease_id == disease_id
                ).first()
            elif image_type == 'zip':
                existing_task = db_session.query(Task).filter(
                    Task.encounter_file_id == image_id,
                    Task.disease_id == disease_id
                ).first()
            
            if existing_task:
                # Skip if task already exists
                skipped_tasks.append({
                    'image_id': image_id,
                    'disease_id': disease_id,
                    'reason': 'task already exists'
                })
                continue
            
            # Create new task based on image type
            if image_type == 'direct':
                new_task = Task(
                    direct_image_upload_id=image_id,
                    disease_id=disease_id,
                    lab_unit_id=lab_unit_id,
                    state='pending',
                    created_at=datetime.utcnow()
                )
            elif image_type == 'zip':
                new_task = Task(
                    encounter_file_id=image_id,
                    disease_id=disease_id,
                    lab_unit_id=lab_unit_id,
                    state='pending',
                    created_at=datetime.utcnow()
                )
            else:
                continue  # Invalid image type
            
            db_session.add(new_task)
            db_session.flush()  # Get the ID for the new task
            
            created_tasks.append({
                'task_id': new_task.id,
                'image_id': image_id,
                'disease_id': disease_id
            })
    
    return {
        'created_tasks': created_tasks,
        'skipped_tasks': skipped_tasks,
        'total_created': len(created_tasks),
        'total_skipped': len(skipped_tasks)
    }