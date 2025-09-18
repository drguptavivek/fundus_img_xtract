"""
Utility functions for retrieving paginated list of gradings done by a user.
"""

from typing import Dict
from sqlalchemy.orm import selectinload
from models import Grade, GradingTask, Disease, DiseaseGrading, LabUnit, Hospital, User, UserDiseaseUnitRole, EncounterFile, DirectImageUpload


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