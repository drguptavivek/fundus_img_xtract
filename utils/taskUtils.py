"""Utility functions for managing tasks and related information.

This module provides centralized functions for retrieving and managing task information,
with proper scoping based on user's lab units and role-based access controls.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session, joinedload
from flask_login import current_user

from models import (
    GradingTask as Task,
    EncounterFile as Image,
    PatientEncounters as Encounter,
    User,
    LabUnit,
    Hospital,
    Camera,
    Disease,
    DiseaseGrading,
    Session as DBSession,
    Grade,
    Consensus,
    DirectImageUpload,
    UserDiseaseUnitRole
)
from utils.hospital_scoping import apply_scoping


def get_task_summary(
    db_session,
    page: int = 1,
    per_page: int = 50,
    lab_unit_ids: Optional[List[int]] = None,
    status_filter: Optional[str] = None,
    disease_filter: Optional[int] = None,
    search_query: Optional[str] = None,
    hospital_filter: Optional[int] = None,
    lab_unit_name_filter: Optional[str] = None,
    lab_unit_filter: Optional[int] = None
) -> Tuple[List[Dict[str, Any]], int]:
    """Get paginated list of tasks with key information.
    
    Args:
        db_session: Database session to use for queries
        page: Page number for pagination (1-indexed), default is 1
        per_page: Number of items per page, default is 50
        lab_unit_ids: List of lab unit IDs to scope the query to
        status_filter: Optional status to filter tasks (e.g., 'pending', 'completed', 'in_progress', 'final')
        disease_filter: Optional disease ID to filter tasks
        search_query: Optional search term to match against image UUID or patient info
        hospital_filter: Optional hospital ID to filter tasks
        lab_unit_name_filter: Optional lab unit name to filter tasks (deprecated - using lab_unit_filter instead)
        lab_unit_filter: Optional lab unit ID to filter tasks
    
    Returns:
        Tuple of (list of task dictionaries, total count)
    """
    # Calculate offset for pagination
    offset = (page - 1) * per_page
    
    # Base query for tasks with eager loads to avoid N+1s.
    # Avoid explicit joins here because apply_scoping() adds its own joins.
    query = db_session.query(Task).options(
        joinedload(Task.disease),
        joinedload(Task.lab_unit).joinedload(LabUnit.hospital),
        joinedload(Task.encounter_file),
        joinedload(Task.direct_image),
    )
    
    # Apply scoping based on user's lab units or admin override
    query = apply_scoping(query, Task, current_user, "analytics")
    
    # Apply optional filters
    if status_filter:
        query = query.filter(Task.state == status_filter)
        
    if disease_filter:
        query = query.filter(Task.disease_id == disease_filter)
        
    if hospital_filter:
        query = query.filter(Task.lab_unit.has(LabUnit.hospital_id == hospital_filter))
        
    if lab_unit_filter:
        query = query.filter(Task.lab_unit_id == lab_unit_filter)
        
    if lab_unit_name_filter:
        query = query.filter(Task.lab_unit.has(LabUnit.name.ilike(f'%{lab_unit_name_filter}%')))
        
    if search_query:
        query = query.filter(
            or_(
                Task.encounter_file.has(
                    or_(
                        Image.uuid.contains(search_query),
                        Image.patient_encounter.has(Encounter.patient_id.contains(search_query)),
                    )
                ),
                Task.direct_image.has(DirectImageUpload.uuid.contains(search_query)),
            )
        )
    
    # Count total before applying pagination
    total_count = query.count()
    
    # Apply ordering and pagination
    tasks = query.order_by(Task.created_at.desc()).offset(offset).limit(per_page).all()
    
    # Format the results
    task_list = []
    for task in tasks:
        # Determine the image UUID based on which relationship exists
        image_uuid = None
        if task.encounter_file:
            image_uuid = task.encounter_file.uuid
        elif task.direct_image:
            image_uuid = task.direct_image.uuid
        else:
            image_uuid = 'Unknown'

        task_dict = {
            'id': task.id,
            'uuid': str(task.id),  # GradingTask doesn't have a uuid field, so using the ID
            'status': task.state,
            'disease': task.disease.name if task.disease else 'Unknown',
            'lab_unit': task.lab_unit.name if task.lab_unit else 'Unknown',
            'hospital': task.lab_unit.hospital.name if task.lab_unit and task.lab_unit.hospital else 'Unknown',
            'image_uuid': image_uuid,
            'image_type': 'direct' if task.direct_image else 'zip' if task.encounter_file else 'Unknown',
            'created_at': task.created_at,
            'updated_at': task.updated_at,
            # GradingTask doesn't have due_date or assigned_to fields like a regular Task would have
        }
        task_list.append(task_dict)
    
    return task_list, total_count


def get_task_detail(db_session, task_id: int, mask_pii_override: bool = False) -> Optional[Dict[str, Any]]:
    """Get detailed information about a specific task including grades and consensus.
    
    Args:
        db_session: Database session to use for queries
        task_id: ID of the task to retrieve details for
        mask_pii_override: If True, always mask PII regardless of user role/hospital
    
    Returns:
        Dictionary with task details or None if task not found
        
    Note:
        PII (patient_id, patient_name) is masked for cross-hospital access.
        Reference: docs/PII_Exposure_Control_Policy.md Section 4.2
    """
    from sqlalchemy.orm import joinedload
    from utils.pii_masking import should_mask_pii, mask_patient_id, mask_patient_name
    # Apply scoping to ensure task belongs to user's hospital/lab units
    query = apply_scoping(db_session.query(Task), Task, current_user, "analytics")
    task = query.filter(Task.id == task_id).options(
        joinedload(Task.consensus),  # Load consensus information
        joinedload(Task.grades)
    ).first()
    
    if not task:
        return None

    # Determine if PII should be masked based on hospital context
    current_user_hospital_id = current_user.hospital_id if current_user.is_authenticated else None
    task_hospital_id = task.lab_unit.hospital_id if task.lab_unit else None
    
    mask_pii = True  # Default to masking for safety
    
    if mask_pii_override:
        mask_pii = True
    elif current_user.is_authenticated:
        user_roles = [r.name for r in current_user.roles]
        
        # 1. Global Admin always sees PII
        if 'admin' in user_roles:
            mask_pii = False
        # 2. Users with roles: Check using optimistic permission (if ANY role allows access, allow it)
        elif user_roles:
            # We check if there is ANY role that results in should_mask_pii returning False
            # If so, we do NOT mask (mask_pii = False)
            # Effectively, mask_pii is True only if ALL roles require masking
            mask_pii = all(
                should_mask_pii(
                    current_user_hospital_id=current_user_hospital_id,
                    data_hospital_id=task_hospital_id,
                    current_user_role=role
                )
                for role in user_roles
            )
        # 3. Users without roles (if any)
        else:
            mask_pii = should_mask_pii(
                current_user_hospital_id=current_user_hospital_id,
                data_hospital_id=task_hospital_id,
                current_user_role=None
            )
    else:
        # Unauthenticated users always masked (though should be caught by auth middleware)
        mask_pii = True
    
    # Collect grading information from the task
    grades = []
    for grade in task.grades:
        grade_dict = {
            'id': grade.id,
            'disease': task.disease.name if task.disease else 'Unknown',
            'impression': grade.grade_name or 'No impression',  # Using denormalized field directly
            'role_slot': grade.role_slot,
            'comment': grade.comment,
            'graded_by': grade.grader.username if grade.grader else 'System',
            'graded_at': grade.created_at,
            'grading_method': grade.role_slot,
            'grader_username': grade.grader.username if grade.grader else None
        }
        grades.append(grade_dict)
    
    # Get consensus information
    # Only consider consensus as existing if there's an actual consensus record
    has_consensus = task.consensus is not None
    
    consensus_info = {
        'has_consensus': has_consensus,
        'consensus_grading': None,
        'consensus_method': task.consensus.method if task.consensus else None,
        'arbitrator_note': None  # Not available in the current models
    }
    
    if task.consensus:
        consensus_info['consensus_grading'] = {
            'disease': task.disease.name if task.disease else 'Unknown',
            'impression': task.consensus.final_grade_name or 'No impression',  # Using only the denormalized field from consensus table
            'grading_value': task.consensus.final_grade_name,
            'grading_severity': task.consensus.final_grade_description,
            'confirmed_by': task.consensus.decided_by.username if task.consensus.decided_by else 'Unknown',
            'confirmed_at': task.consensus.decided_at
        }
    
    # Build the detailed task dictionary
    # Determine image info based on which relationship exists
    image_info = {}
    if task.encounter_file:
        raw_patient_id = task.encounter_file.patient_id if hasattr(task.encounter_file, 'patient_id') else 'Unknown'
        raw_patient_name = task.encounter_file.patient_name if hasattr(task.encounter_file, 'patient_name') else 'Unknown'
        
        image_info = {
            'image_uuid': task.encounter_file.uuid,
            'image_path': None,  # Doesn't exist in this model
            'patient_id': mask_patient_id(raw_patient_id) if mask_pii else raw_patient_id,
            'patient_name': mask_patient_name() if mask_pii else raw_patient_name
        }
    elif task.direct_image:
        image_info = {
            'image_uuid': task.direct_image.uuid,
            'image_path': f"{task.direct_image.folder_rel}/{task.direct_image.filename}",
            'patient_id': 'Unknown',  # Not available for direct uploads
            'patient_name': 'Unknown'  # Not available for direct uploads
        }
    else:
        image_info = {
            'image_uuid': 'Unknown',
            'image_path': 'Unknown',
            'patient_id': 'Unknown',
            'patient_name': 'Unknown'
        }
    
    task_detail = {
        'id': task.id,
        'uuid': str(task.id),  # Using ID as GradingTask doesn't have a UUID field
        'status': task.state,
        'disease': task.disease.name if task.disease else 'Unknown',
        'lab_unit': task.lab_unit.name if task.lab_unit else 'Unknown',
        'hospital': task.lab_unit.hospital.name if task.lab_unit and task.lab_unit.hospital else 'Unknown',
        'image_uuid': image_info['image_uuid'],
        'image_path': image_info['image_path'],
        'patient_id': image_info['patient_id'],
        'patient_name': image_info['patient_name'],
        'patient_age': 'Unknown',  # Not available in these models
        'patient_sex': 'Unknown',  # Not available in these models
        'created_at': task.created_at,
        'updated_at': task.updated_at,
        'assigned_to': None,  # GradingTask doesn't have an assigned_to field
        'created_by': None,  # GradingTask doesn't have a created_by field
        'due_date': None,  # GradingTask doesn't have a due_date
        'priority': None,  # GradingTask doesn't have a priority
        'notes': None,  # GradingTask doesn't have notes
        'grades': grades,
        'consensus_info': consensus_info,
        'camera_type': task.direct_image.camera.name if task.direct_image and task.direct_image.camera else 'Unknown'
    }
    
    return task_detail


def get_tasks_by_status(
    db_session,
    status: str, 
    lab_unit_ids: Optional[List[int]] = None,
    page: int = 1,
    per_page: int = 50
) -> Tuple[List[Dict[str, Any]], int]:
    """Get tasks filtered by status.
    
    Args:
        db_session: Database session to use for queries
        status: Status to filter by (e.g., 'pending', 'completed', 'in_progress', 'final')
        lab_unit_ids: List of lab unit IDs to scope the query to
        page: Page number for pagination (1-indexed), default is 1
        per_page: Number of items per page (default 50)
    
    Returns:
        Tuple of (list of task dictionaries, total count)
    """
    # Calculate offset for pagination
    offset = (page - 1) * per_page

    # Join with appropriate image association
    query = db_session.query(Task).join(LabUnit).join(Disease).outerjoin(Image, Task.encounter_file_id == Image.id).outerjoin(DirectImageUpload, Task.direct_image_upload_id == DirectImageUpload.id)
    
    # Apply scoping based on user's lab units or admin override
    query = apply_scoping(query, Task, current_user, "analytics")
    
    # Apply status filter (state in the case of GradingTask)
    query = query.filter(Task.state == status)
    
    # Count total before applying pagination
    total_count = query.count()
    
    # Apply ordering and pagination
    tasks = query.order_by(Task.created_at.desc()).offset(offset).limit(per_page).all()
    
    # Format the results
    task_list = []
    for task in tasks:
        # Determine the image UUID based on which relationship exists
        image_uuid = None
        if task.encounter_file:
            image_uuid = task.encounter_file.uuid
        elif task.direct_image:
            image_uuid = task.direct_image.uuid
        else:
            image_uuid = 'Unknown'

        task_dict = {
            'id': task.id,
            'uuid': str(task.id),  # Using ID as GradingTask doesn't have a UUID field
            'status': task.state,
            'disease': task.disease.name if task.disease else 'Unknown',
            'lab_unit': task.lab_unit.name if task.lab_unit else 'Unknown',
            'image_uuid': image_uuid,
            'assigned_to': None,  # GradingTask doesn't have an assigned_to field
            'created_at': task.created_at,
            'due_date': None  # GradingTask doesn't have a due_date field
        }
        task_list.append(task_dict)
    
    return task_list, total_count


def get_task_stats(db_session, lab_unit_ids: Optional[List[int]] = None) -> Dict[str, int]:
    """Get task statistics for specified lab units.
    
    Args:
        db_session: Database session to use for queries
        lab_unit_ids: List of lab unit IDs to get stats for
    
    Returns:
        Dictionary with task statistics
    """
    query = db_session.query(Task)
    
    # Apply scoping based on user's lab units or admin override
    query = apply_scoping(query, Task, current_user, "analytics")
    
    # Count all tasks
    total_tasks = query.count()
    
    # Count tasks by state (status in GradingTask)
    pending_count = query.filter(Task.state == 'pending').count()
    in_progress_count = query.filter(Task.state.in_(['resident_done', 'resident2_done'])).count()
    completed_count = query.filter(Task.state == 'final').count()
    # For GradingTask, we can consider 'arbitration' state as overdue if needed
    overdue_count = 0  # GradingTask doesn't have a due_date field, so we can't calculate
    
    return {
        'total_tasks': total_tasks,
        'pending_tasks': pending_count,
        'in_progress_tasks': in_progress_count,
        'completed_tasks': completed_count,
        'overdue_tasks': overdue_count
    }


def get_tasks_for_user(
    db_session,
    user_id: int,
    page: int = 1,
    per_page: int = 50,
    status_filter: Optional[str] = None
) -> Tuple[List[Dict[str, Any]], int]:
    """Get tasks eligible for a specific user based on their permissions.
    
    In this system, tasks are not assigned but users get tasks based on their 
    LabUnit-Disease-slot eligibility mapping.
    
    Args:
        db_session: Database session to use for queries
        user_id: ID of the user to get eligible tasks for
        page: Page number for pagination (1-indexed), default is 1
        per_page: Number of items per page (default 50)
        status_filter: Optional status to filter tasks
    
    Returns:
        Tuple of (list of task dictionaries, total count)
    """
    # Calculate offset for pagination
    offset = (page - 1) * per_page

    # Get the user's eligible lab units, diseases, and role permissions
    user_disease_unit_roles = db_session.query(UserDiseaseUnitRole).filter(
        UserDiseaseUnitRole.user_id == user_id,
        UserDiseaseUnitRole.active == True
    ).all()
    
    # Extract the eligible combinations
    eligible_combinations = []
    for role in user_disease_unit_roles:
        eligible_combinations.append({
            'lab_unit_id': role.lab_unit_id,
            'disease_id': role.disease_id
        })
    
    if not eligible_combinations:
        # If user has no eligible combinations, return empty list
        return [], 0
    
    # Group by lab_unit_id and disease_id to form query filters
    lab_unit_ids = list(set([combo['lab_unit_id'] for combo in eligible_combinations]))
    disease_ids = list(set([combo['disease_id'] for combo in eligible_combinations]))
    
    # Base query for tasks
    query = db_session.query(Task).join(LabUnit).join(Disease).outerjoin(Image, Task.encounter_file_id == Image.id).outerjoin(DirectImageUpload, Task.direct_image_upload_id == DirectImageUpload.id)
    
    # Filter by the user's eligible lab units and diseases
    query = query.filter(
        Task.lab_unit_id.in_(lab_unit_ids),
        Task.disease_id.in_(disease_ids)
    )
    
    # Apply scoping based on current user's lab units or admin override
    query = apply_scoping(query, Task, current_user, "analytics")
    
    # Apply optional status filter
    if status_filter:
        query = query.filter(Task.state == status_filter)
    
    # Count total before applying pagination
    total_count = query.count()
    
    # Apply ordering and pagination
    tasks = query.order_by(Task.created_at.desc()).offset(offset).limit(per_page).all()
    
    # Format the results
    task_list = []
    for task in tasks:
        # Determine the image UUID based on which relationship exists
        image_uuid = None
        if task.encounter_file:
            image_uuid = task.encounter_file.uuid
        elif task.direct_image:
            image_uuid = task.direct_image.uuid
        else:
            image_uuid = 'Unknown'

        task_dict = {
            'id': task.id,
            'uuid': str(task.id),  # Using ID as GradingTask doesn't have a UUID field
            'status': task.state,
            'disease': task.disease.name if task.disease else 'Unknown',
            'lab_unit': task.lab_unit.name if task.lab_unit else 'Unknown',
            'image_uuid': image_uuid,
            'created_at': task.created_at,
            'updated_at': task.updated_at,
            'due_date': None,  # GradingTask doesn't have a due_date
            'priority': None  # GradingTask doesn't have a priority
        }
        task_list.append(task_dict)
    
    return task_list, total_count
