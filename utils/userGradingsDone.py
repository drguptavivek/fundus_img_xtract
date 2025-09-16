"""
Utility functions for retrieving paginated list of gradings done by a user.
"""

from typing import List, Tuple, Optional, Dict, Any
from sqlalchemy import desc
from sqlalchemy.orm import selectinload
from models import Session, Grade, GradingTask, Disease, DiseaseGrading, LabUnit, Hospital, User, UserDiseaseUnitRole, EncounterFile, DirectImageUpload


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
    finally:
        session.close()


def get_user_kpi_completed_task_count_data(user_id: int) -> Dict[str, Dict[str, int]]:
    """
    Get KPI data for each core disease for completed tasks across all mapped lab units for each slot of a user.
    
    This function provides a comprehensive view of completed tasks by disease for all eligible slots
    (resident, faculty, arbitration) across all lab units where the user has eligibility.
    
    Args:
        user_id: The ID of the user
        
    Returns:
        A dictionary with disease names as keys and slot counts as values:
        {
            'Disease Name': {
                'resident_completed': count,
                'faculty_completed': count,
                'arbitration_completed': count
            },
            ...
        }
    """
    db = Session()
    try:
        # Get user with roles
        user = db.query(User).options(selectinload(User.roles)).filter(User.id == user_id).first()
        if not user:
            return {}
        
        # Get all diseases
        diseases = db.query(Disease).all()
        disease_names = {disease.id: disease.name for disease in diseases}
        
        # Check if user has the required roles
        has_resident_role = user.has_role('resident')
        has_faculty_role = user.has_role('ophthalmologist')
        
        # Get diseases where user has actually completed gradings
        user_graded_diseases = db.query(GradingTask.disease_id).join(Grade, Grade.task_id == GradingTask.id).filter(
            Grade.grader_user_id == user_id
        ).distinct().all()
        
        user_graded_disease_ids = [d[0] for d in user_graded_diseases]
        
        # If user hasn't graded anything, return empty
        if not user_graded_disease_ids:
            return {}
        
        # Calculate task counts for each disease where user has completed gradings
        kpi_data = {}
        
        for disease_id in user_graded_disease_ids:
            disease_name = disease_names.get(disease_id, f"Unknown Disease {disease_id}")
            
            counts = {
                'resident_completed': 0,
                'faculty_completed': 0,
                'arbitration_completed': 0
            }
            
            # Count resident completed tasks
            if has_resident_role:
                counts['resident_completed'] = db.query(Grade).filter(
                    Grade.grader_user_id == user_id,
                    Grade.role_slot == 'resident',
                    Grade.task.has(GradingTask.disease_id == disease_id)
                ).count()
            
            # Count faculty completed tasks
            if has_faculty_role:
                counts['faculty_completed'] = db.query(Grade).filter(
                    Grade.grader_user_id == user_id,
                    Grade.role_slot == 'faculty',
                    Grade.task.has(GradingTask.disease_id == disease_id)
                ).count()
            
            # Count arbitration completed tasks
            if has_faculty_role:
                counts['arbitration_completed'] = db.query(Grade).filter(
                    Grade.grader_user_id == user_id,
                    Grade.role_slot == 'arbitrator',
                    Grade.task.has(GradingTask.disease_id == disease_id)
                ).count()
            
            kpi_data[disease_name] = counts
        
        return kpi_data
    finally:
        db.close()