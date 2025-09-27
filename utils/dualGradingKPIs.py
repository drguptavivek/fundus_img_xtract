"""
Utility functions for dual grading operations.

Note: All functions in this module expect a database session to be passed as a parameter.
The caller is responsible for managing the session lifecycle (opening and closing).
This design allows for better transaction management and session reuse.
"""

from sqlalchemy.orm import selectinload
from sqlalchemy import and_, or_
from models import GradingTask, User, UserDiseaseUnitRole, EncounterFile, DirectImageUpload, Disease, LabUnit, Grade, DiseaseGrading
from typing import Dict, Optional, List, Tuple


def get_user_kpi_pending_task_count_data(db, user_id: int) -> Dict[str, Dict[str, int]]:
    """
    Get KPI data for each core disease for pending tasks across all mapped lab units for each slot of a user.
    
    This function provides a comprehensive view of pending tasks by disease for all eligible slots
    (resident, faculty, arbitration) across all lab units where the user has eligibility.
    
    Args:
        db: Database session (caller is responsible for closing)
        user_id: The ID of the user
        
    Returns:
        A dictionary with disease names as keys and slot counts as values:
        {
            'Disease Name': {
                'resident_pending': count,
                'faculty_pending': count,
                'arbitration_pending': count
            },
            ...
        }
    """
    # Get user with roles
    user = db.query(User).options(selectinload(User.roles)).filter(User.id == user_id).first()
    if not user:
        return {}
    
    # Get all diseases
    diseases = db.query(Disease).all()
    disease_names = {disease.id: disease.name for disease in diseases}
    
    # Get user's eligible roles
    eligible_roles = db.query(UserDiseaseUnitRole).filter(
        UserDiseaseUnitRole.user_id == user_id,
        UserDiseaseUnitRole.active == True
    ).all()
    
    if not eligible_roles:
        return {}
    
    # Group eligible lab units by disease
    disease_lab_units = {}
    for role in eligible_roles:
        if role.disease_id not in disease_lab_units:
            disease_lab_units[role.disease_id] = {
                'lab_units': set(),
                'can_grade_resident': False,
                'can_grade_faculty': False,
                'can_arbitrate': False
            }
        disease_lab_units[role.disease_id]['lab_units'].add(role.lab_unit_id)
        disease_lab_units[role.disease_id]['can_grade_resident'] |= role.can_grade_resident
        disease_lab_units[role.disease_id]['can_grade_faculty'] |= role.can_grade_faculty
        disease_lab_units[role.disease_id]['can_arbitrate'] |= role.can_arbitrate
    
    # Calculate task counts for each disease
    kpi_data = {}
    
    # For all users (including admins), only include diseases where they have eligibility
    for disease_id, info in disease_lab_units.items():
        disease_name = disease_names.get(disease_id, f"Unknown Disease {disease_id}")
        lab_unit_ids = list(info['lab_units'])
        
        counts = {
            'resident_pending': 0,
            'faculty_pending': 0,
            'arbitration_pending': 0
        }
        
        # Check if user has the required roles
        has_resident_role = user.has_role('resident')
        has_faculty_role = user.has_role('ophthalmologist')
        
        # Count resident pending tasks (only if user is resident and has resident eligibility)
        if has_resident_role and info['can_grade_resident']:
            counts['resident_pending'] = db.query(GradingTask).filter(
                GradingTask.state == 'pending',
                GradingTask.lab_unit_id.in_(lab_unit_ids),
                GradingTask.disease_id == disease_id
            ).count()
        
        # Count faculty pending tasks (only if user is faculty and has faculty eligibility)
        if has_faculty_role and info['can_grade_faculty']:
            counts['faculty_pending'] = db.query(GradingTask).filter(
                GradingTask.state == 'resident_done',
                GradingTask.lab_unit_id.in_(lab_unit_ids),
                GradingTask.disease_id == disease_id
            ).count()
        
        # Count arbitration pending tasks (only if user is faculty and has arbitration eligibility)
        if has_faculty_role and info['can_arbitrate']:
            # Get tasks in arbitration state
            arbitration_tasks = db.query(GradingTask).filter(
                GradingTask.state == 'arbitration',
                GradingTask.lab_unit_id.in_(lab_unit_ids),
                GradingTask.disease_id == disease_id
            ).all()
            
            # Apply same filtering as in task assignment to exclude tasks user recently graded
            from utils.dualGradingGetNextTasks import _has_user_graded_task_recently
            eligible_arbitration_tasks = []
            for task in arbitration_tasks:
                if not _has_user_graded_task_recently(db, user_id, task.id):
                    eligible_arbitration_tasks.append(task)
            
            counts['arbitration_pending'] = len(eligible_arbitration_tasks)
        
        kpi_data[disease_name] = counts
    
    return kpi_data


def get_user_kpi_completed_task_count_data(db, user_id: int) -> Dict[str, Dict[str, int]]:
    """
    Get KPI data for each core disease for completed tasks across all mapped lab units for each slot of a user.
    
    This function provides a comprehensive view of completed tasks by disease for all eligible slots
    (resident, faculty, arbitration) across all lab units where the user has eligibility.
    
    Args:
        db: Database session (caller is responsible for closing)
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