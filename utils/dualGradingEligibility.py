"""
Utility functions for retrieving user grading eligibility details.

Note: All functions in this module expect a database session to be passed as a parameter.
The caller is responsible for managing the session lifecycle (opening and closing).
This design allows for better transaction management and session reuse.
"""

from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from models import Grade, User, Disease, LabUnit, UserDiseaseUnitRole, Hospital, GradingTask


def get_user_grading_eligibility_details(db, user_id: int) -> Dict[str, Any]:
    """
    Get detailed grading eligibility information for a user with lab unit and disease names.
    
    Args:
        db: Database session (caller is responsible for closing)
        user_id (int): ID of the user
        
    Returns:
        Dict containing user eligibility details grouped by hospital, then lab unit, then disease
    """
    user = db.get(User, user_id)
    if not user:
        return {}
        
    # Get all diseases and lab units for reference
    diseases = {d.id: d.name for d in db.execute(select(Disease)).scalars().all()}
    lab_units = {lu.id: {'name': lu.name, 'hospital_id': lu.hospital_id} for lu in db.execute(select(LabUnit)).scalars().all()}
    hospitals = {}  # We'll fetch hospital names as needed
    
    rows = db.execute(
        select(UserDiseaseUnitRole)
        .where(UserDiseaseUnitRole.user_id == user_id)
        .where(UserDiseaseUnitRole.active == True)
    ).scalars().all()
    
    # Group by hospital first, then by lab unit
    grouped = {}
    for r in rows:
        if r.can_grade_resident or r.can_grade_resident2 or r.can_arbitrate:
            lab_unit_id = r.lab_unit_id
            disease_id = r.disease_id
            
            # Get hospital info
            hospital_id = lab_units[lab_unit_id]['hospital_id']
            if hospital_id not in hospitals:
                hospital = db.get(Hospital, hospital_id)
                hospitals[hospital_id] = hospital.name if hospital else 'Unknown Hospital'
            
            hospital_name = hospitals[hospital_id]
            
            # Initialize hospital group if not exists
            if hospital_name not in grouped:
                grouped[hospital_name] = {}
            
            # Initialize lab unit group if not exists
            lab_unit_name = lab_units[lab_unit_id]['name']
            if lab_unit_name not in grouped[hospital_name]:
                grouped[hospital_name][lab_unit_name] = {}
            
            # Initialize disease group if not exists
            disease_name = diseases.get(disease_id, 'Unknown Disease')
            if disease_name not in grouped[hospital_name][lab_unit_name]:
                grouped[hospital_name][lab_unit_name][disease_name] = []
            
            # Add roles
            if r.can_grade_resident:
                grouped[hospital_name][lab_unit_name][disease_name].append('Resident')
            if r.can_grade_resident2:
                grouped[hospital_name][lab_unit_name][disease_name].append('Resident2')
            if r.can_arbitrate:
                grouped[hospital_name][lab_unit_name][disease_name].append('Arbitrator')
    
    return grouped


def _get_user_eligible_lab_unit_ids(db, user_id: int, disease_id: int, role_slot: str) -> Optional[list]:
    """
    Get the list of lab unit IDs that a user is eligible for a specific role and disease.
    
    Args:
        db: Database session
        user_id: The ID of the user
        disease_id: The disease ID
        role_slot: The role slot ('resident', 'resident2', or 'arbitrator')
        
    Returns:
        List of eligible lab unit IDs or None if user has no eligibility
    """
    # Load user with roles
    user = db.query(User).options(selectinload(User.roles)).filter(User.id == user_id).first()
    if not user:
        return None
    
    # Check if user is admin (admins have access to all lab units)
    if user.has_role('admin'):
        lab_units = db.query(LabUnit).all()
        return [lab_unit.id for lab_unit in lab_units]
    
    # Check role-specific permissions
    # Allow both residents and ophthalmologists to do resident grading based on eligibility
    if role_slot == "resident" and not (user.has_role('resident') or user.has_role('ophthalmologist')):
        return None
    elif role_slot in ["resident2", "arbitrator"] and not user.has_role('ophthalmologist'):
        return None
    
    # Build eligibility query based on role slot
    eligibility_query = db.query(UserDiseaseUnitRole).filter(
        UserDiseaseUnitRole.user_id == user_id,
        UserDiseaseUnitRole.disease_id == disease_id,
        UserDiseaseUnitRole.active == True
    )
    
    # Add role-specific filter
    if role_slot == "resident":
        eligibility_query = eligibility_query.filter(UserDiseaseUnitRole.can_grade_resident == True)
    elif role_slot == "resident2":
        eligibility_query = eligibility_query.filter(UserDiseaseUnitRole.can_grade_resident2 == True)
    elif role_slot == "arbitrator":
        eligibility_query = eligibility_query.filter(UserDiseaseUnitRole.can_arbitrate == True)
    
    # Get eligible roles
    eligible_roles = eligibility_query.all()
    if not eligible_roles:
        return None
    
    return [role.lab_unit_id for role in eligible_roles]


def check_arbitration_eligibility(db, user_id: int, disease_id: int, lab_unit_id: int):
    """
    Check if a user is eligible to arbitrate for a specific disease and lab unit.
    
    Args:
        db: Database session (caller is responsible for closing)
        user_id: The ID of the user
        disease_id: The ID of the disease
        lab_unit_id: The ID of the lab unit
        
    Returns:
        UserDiseaseUnitRole object if eligible, None otherwise
    """
    return db.query(UserDiseaseUnitRole).filter(
        UserDiseaseUnitRole.user_id == user_id,
        UserDiseaseUnitRole.disease_id == disease_id,
        UserDiseaseUnitRole.lab_unit_id == lab_unit_id,
        UserDiseaseUnitRole.active == True,
        UserDiseaseUnitRole.can_arbitrate == True
    ).first()


def get_user_eligibility_for_task(db, user_id: int, task_id: int, role_slot: str) -> bool:
    """
    Check if a user is eligible for a specific role slot for a task.
    
    Args:
        db: Database session (caller is responsible for closing)
        user_id: The ID of the user
        task_id: The ID of the task
        role_slot: The role slot ('resident', 'resident2', or 'arbitrator')
        
    Returns:
        True if user is eligible, False otherwise
    """
    # Load task with related data
    task = db.query(GradingTask).options(
        selectinload(GradingTask.disease),
        selectinload(GradingTask.lab_unit)
    ).filter(GradingTask.id == task_id).first()
    
    if not task or not task.disease_id or not task.lab_unit_id:
        return False
        
    # Load user
    user = db.query(User).options(selectinload(User.roles)).filter(User.id == user_id).first()
    if not user:
        return False
        
    # Check role requirements
    # Allow both residents and ophthalmologists to do resident grading based on eligibility
    if role_slot == 'resident' and not (user.has_role('resident') or user.has_role('ophthalmologist')):
        return False
    elif role_slot in ('resident2', 'arbitrator') and not user.has_role('ophthalmologist'):
        return False
        
    # Check eligibility matrix using UserDiseaseUnitRole table
    eligibility_filter = None
    if role_slot == 'resident':
        eligibility_filter = UserDiseaseUnitRole.can_grade_resident == True
    elif role_slot == 'resident2':
        eligibility_filter = UserDiseaseUnitRole.can_grade_resident2 == True
    elif role_slot == 'arbitrator':
        eligibility_filter = UserDiseaseUnitRole.can_arbitrate == True
        
    if eligibility_filter:
        eligibility = db.query(UserDiseaseUnitRole).filter(
            UserDiseaseUnitRole.user_id == user_id,
            UserDiseaseUnitRole.disease_id == task.disease_id,
            UserDiseaseUnitRole.lab_unit_id == task.lab_unit_id,
            UserDiseaseUnitRole.active == True,
            eligibility_filter
        ).first()
        
        if not eligibility:
            return False
        
    return True


def _has_user_graded_task_2weeks(db, user_id: int, task_id: int) -> bool:
    """
    Check if a user has graded a task in the past 2 weeks.
    
    Args:
        db: Database session
        user_id: The ID of the user
        task_id: The ID of the task
        
    Returns:
        True if user has graded the task in the past 2 weeks, False otherwise
    """
    from datetime import timezone
    # Use timezone-aware datetime for comparison
    two_weeks_ago = datetime.now(timezone.utc) - timedelta(weeks=2)
    
    # Get all grades by this user for this task
    user_grades = db.query(Grade).filter(
        Grade.grader_user_id == user_id,
        Grade.task_id == task_id
    ).all()
    
    # Check if any of the grades were created in the last 2 weeks
    for grade in user_grades:
        # Handle timezone-naive datetimes from the database
        grade_created_at = grade.created_at
        if grade_created_at.tzinfo is None:
            # Assume naive datetime is in UTC
            grade_created_at = grade_created_at.replace(tzinfo=timezone.utc)
        
        if grade_created_at >= two_weeks_ago:
            return True
    
    return False
