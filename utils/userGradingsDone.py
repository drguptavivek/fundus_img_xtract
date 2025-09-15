"""
Utility functions for retrieving paginated list of gradings done by a user.
"""

from typing import List, Tuple, Optional, Dict, Any
from sqlalchemy import desc
from models import Session, Grade, GradingTask, Disease, DiseaseGrading, LabUnit, Hospital


def get_user_gradings(
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
        user_id (int): ID of the user
        page (int): Page number (1-indexed)
        per_page (int): Number of items per page
        role_slot (Optional[str]): Filter by role slot (resident, faculty, arbitrator)
        
    Returns:
        Tuple[List[Grade], int]: A tuple containing:
            - List of Grade objects for the current page
            - Total count of gradings by the user
    """
    session = Session()
    try:
        # Base query
        query = session.query(Grade).filter(Grade.grader_user_id == user_id)
        
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
    finally:
        session.close()


def get_user_gradings_with_details(
    user_id: int, 
    page: int = 1, 
    per_page: int = 20,
    role_slot: Optional[str] = None
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Retrieve a paginated list of gradings done by a user with related details.
    
    Args:
        user_id (int): ID of the user
        page (int): Page number (1-indexed)
        per_page (int): Number of items per page
        role_slot (Optional[str]): Filter by role slot (resident, faculty, arbitrator)
        
    Returns:
        Tuple[List[Dict[str, Any]], int]: A tuple containing:
            - List of dictionaries with grading details for the current page
            - Total count of gradings by the user
    """
    session = Session()
    try:
        # Base query with joins for related data
        query = (
            session.query(
                Grade,
                Disease.name.label('disease_name'),
                DiseaseGrading.impression.label('grade_impression'),
                LabUnit.name.label('lab_unit_name'),
                Hospital.name.label('hospital_name')
            )
            .join(GradingTask, Grade.task_id == GradingTask.id)
            .join(Disease, GradingTask.disease_id == Disease.id)
            .join(DiseaseGrading, Grade.disease_grading_id == DiseaseGrading.id)
            .join(LabUnit, GradingTask.lab_unit_id == LabUnit.id)
            .join(Hospital, LabUnit.hospital_id == Hospital.id)
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
                'hospital_name': result.hospital_name
            }
            gradings_with_details.append(grade_dict)
        
        return gradings_with_details, total_count
    finally:
        session.close()