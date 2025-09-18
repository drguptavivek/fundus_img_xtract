"""
Utility functions for working with grades and tasks.

Note: All functions in this module expect a database session to be passed as a parameter.
The caller is responsible for managing the session lifecycle (opening and closing).
This design allows for better transaction management and session reuse.
"""

from typing import List, Tuple, Optional, Dict, Any
from sqlalchemy import desc
from sqlalchemy.orm import selectinload
from models import Grade, GradingTask, Consensus, Disease, DiseaseGrading, LabUnit, Hospital, User, UserDiseaseUnitRole, EncounterFile, DirectImageUpload


def fetch_grade_with_related_data(db, grade_id: int):
    """
    Fetch a grade with all related data.
    
    Args:
        db: Database session (caller is responsible for closing)
        grade_id: The ID of the grade to fetch
        
    Returns:
        Grade object with all related data loaded
    """
    return db.query(Grade).options(
        selectinload(Grade.task).selectinload(GradingTask.disease),
        selectinload(Grade.task).selectinload(GradingTask.encounter_file),
        selectinload(Grade.task).selectinload(GradingTask.direct_image),
        selectinload(Grade.task).selectinload(GradingTask.consensus).selectinload(Consensus.decided_by),
        selectinload(Grade.task).selectinload(GradingTask.consensus).selectinload(Consensus.final_label),
        selectinload(Grade.task).selectinload(GradingTask.grades).selectinload(Grade.grader),
        selectinload(Grade.task).selectinload(GradingTask.grades).selectinload(Grade.label),
        selectinload(Grade.label)
    ).filter(Grade.id == grade_id).first()


def fetch_task_with_related_data(db, task_id: int):
    """
    Fetch a grading task with all related data.
    
    Args:
        db: Database session (caller is responsible for closing)
        task_id: The ID of the task to fetch
        
    Returns:
        GradingTask object with all related data loaded
    """
    return db.query(GradingTask).options(
        selectinload(GradingTask.disease),
        selectinload(GradingTask.encounter_file),
        selectinload(GradingTask.direct_image),
        selectinload(GradingTask.consensus).selectinload(Consensus.decided_by),
        selectinload(GradingTask.consensus).selectinload(Consensus.final_label),
        selectinload(GradingTask.grades).selectinload(Grade.grader),
        selectinload(GradingTask.grades).selectinload(Grade.label)
    ).filter(GradingTask.id == task_id).first()


def fetch_existing_grade_for_user(db, task_id: int, user_id: int, slot_type: str):
    """
    Fetch existing grade for this user and slot (for review purposes).
    
    Args:
        db: Database session (caller is responsible for closing)
        task_id: The ID of the task
        user_id: The ID of the user
        slot_type: The slot type (resident, faculty, arbitrator)
        
    Returns:
        Grade object if found, None otherwise
    """
    return db.query(Grade).filter(
        Grade.task_id == task_id,
        Grade.grader_user_id == user_id,
        Grade.role_slot == slot_type
    ).first()


def get_user_gradings(
    db,
    user_id: int, 
    page: int = 1, 
    per_page: int = 20,
    role_slot: Optional[str] = None
) -> Tuple[List[Grade], int]:
    """
    Retrieve a paginated list of gradings done by a user.
    
    This function returns Grade model objects. For a version that includes
    related details like disease name, lab unit name, etc., see 
    get_user_gradings_with_details().
    
    Args:
        db: Database session (caller is responsible for closing)
        user_id (int): ID of the user
        page (int): Page number (1-indexed)
        per_page (int): Number of items per page
        role_slot (Optional[str]): Filter by role slot (resident, faculty, arbitrator)
        
    Returns:
        Tuple[List[Grade], int]: A tuple containing:
            - List of Grade objects for the current page
            - Total count of gradings by the user
    """
    # Base query
    query = db.query(Grade).filter(Grade.grader_user_id == user_id)
    
    # Filter by role slot if provided
    if role_slot:
        query = query.filter(Grade.role_slot == role_slot)
    
    # Order by created_at descending (most recent first)
    query = query.order_by(desc(Grade.created_at))
    
    # Get total count
    total_count = query.count()
    
    # Apply pagination
    offset = (page - 1) * per_page
    gradings = query.offset(offset).limit(per_page).all()
    
    return gradings, total_count


def get_user_gradings_with_details(
    db,
    user_id: int, 
    page: int = 1, 
    per_page: int = 20,
    role_slot: Optional[str] = None
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Retrieve a paginated list of gradings done by a user with related details.
    
    Args:
        db: Database session (caller is responsible for closing)
        user_id (int): ID of the user
        page (int): Page number (1-indexed)
        per_page (int): Number of items per page
        role_slot (Optional[str]): Filter by role slot (resident, faculty, arbitrator)
        
    Returns:
        Tuple[List[Dict[str, Any]], int]: A tuple containing:
            - List of dictionaries with grading details for the current page
            - Total count of gradings by the user
    """
    # Base query with joins for related data
    query = (
        db.query(
            Grade,
            Disease.name.label('disease_name'),
            DiseaseGrading.impression.label('grade_impression'),
            LabUnit.name.label('lab_unit_name'),
            Hospital.name.label('hospital_name'),
            EncounterFile.uuid.label('encounter_file_uuid'),
            DirectImageUpload.uuid.label('direct_image_uuid')
        )
        .join(GradingTask, Grade.task_id == GradingTask.id)
        .join(Disease, GradingTask.disease_id == Disease.id)
        .join(DiseaseGrading, Grade.disease_grading_id == DiseaseGrading.id)
        .join(LabUnit, GradingTask.lab_unit_id == LabUnit.id)
        .join(Hospital, LabUnit.hospital_id == Hospital.id)
        .outerjoin(EncounterFile, GradingTask.encounter_file_id == EncounterFile.id)
        .outerjoin(DirectImageUpload, GradingTask.direct_image_upload_id == DirectImageUpload.id)
        .filter(Grade.grader_user_id == user_id)
    )
    
    # Filter by role slot if provided
    if role_slot:
        query = query.filter(Grade.role_slot == role_slot)
    
    # Order by created_at descending (most recent first)
    query = query.order_by(desc(Grade.created_at))
    
    # Get total count
    total_count = query.count()
    
    # Apply pagination
    offset = (page - 1) * per_page
    results = query.offset(offset).limit(per_page).all()
    
    # Process results to create dictionaries with all needed information
    gradings_with_details = []
    for result in results:
        # Determine the image UUID
        image_uuid = None
        if result.encounter_file_uuid:
            image_uuid = result.encounter_file_uuid
        elif result.direct_image_uuid:
            image_uuid = result.direct_image_uuid
        
        grade_dict = {
            'id': result.Grade.id,
            'task_id': result.Grade.task_id,
            'grader_user_id': result.Grade.grader_user_id,
            'role_slot': result.Grade.role_slot,
            'disease_grading_id': result.Grade.disease_grading_id,
            'comment': result.Grade.comment,
            'created_at': result.Grade.created_at,
            'updated_at': result.Grade.updated_at,
            'disease_name': result.disease_name,
            'grade_impression': result.grade_impression,
            'lab_unit_name': result.lab_unit_name,
            'hospital_name': result.hospital_name,
            'image_uuid': image_uuid
        }
        gradings_with_details.append(grade_dict)
    
    return gradings_with_details, total_count