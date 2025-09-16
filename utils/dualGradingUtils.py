"""
Utility functions for dual grading operations.
"""

from sqlalchemy.orm import selectinload
from sqlalchemy import and_, or_
from models import Session, GradingTask, User, UserDiseaseUnitRole, EncounterFile, DirectImageUpload, Disease, LabUnit
from typing import Dict, Optional, List, Tuple


def get_user_kpi_pending_task_count_data(user_id: int) -> Dict[str, Dict[str, int]]:
    """
    Get KPI data for each core disease for pending tasks across all mapped lab units for each slot of a user.
    
    This function provides a comprehensive view of pending tasks by disease for all eligible slots
    (resident, faculty, arbitration) across all lab units where the user has eligibility.
    
    Args:
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
    db = Session()
    try:
        # Get user with roles
        user = db.query(User).options(selectinload(User.roles)).filter(User.id == user_id).first()
        if not user:
            return {}
        
        # Check if user is admin
        is_admin = user.has_role('admin')
        
        # Get all diseases
        diseases = db.query(Disease).all()
        disease_names = {disease.id: disease.name for disease in diseases}
        
        # For admins, get all lab units; for regular users, get only eligible lab units
        if is_admin:
            all_lab_unit_ids = [lab_unit.id for lab_unit in db.query(LabUnit).all()]
        
        # Get user's eligible roles
        if is_admin:
            # Admins can see all diseases and lab units
            eligible_roles = db.query(UserDiseaseUnitRole).filter(
                UserDiseaseUnitRole.active == True
            ).all()
        else:
            eligible_roles = db.query(UserDiseaseUnitRole).filter(
                UserDiseaseUnitRole.user_id == user_id,
                UserDiseaseUnitRole.active == True
            ).all()
        
        if not eligible_roles and not is_admin:
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
        
        # For admins, include all diseases even if they have no explicit eligibility
        if is_admin:
            for disease_id, disease_name in disease_names.items():
                lab_unit_ids = all_lab_unit_ids
                
                counts = {
                    'resident_pending': 0,
                    'faculty_pending': 0,
                    'arbitration_pending': 0
                }
                
                # Count resident pending tasks
                counts['resident_pending'] = db.query(GradingTask).filter(
                    GradingTask.state == 'pending',
                    GradingTask.lab_unit_id.in_(lab_unit_ids),
                    GradingTask.disease_id == disease_id
                ).count()
                
                # Count faculty pending tasks
                counts['faculty_pending'] = db.query(GradingTask).filter(
                    GradingTask.state == 'resident_done',
                    GradingTask.lab_unit_id.in_(lab_unit_ids),
                    GradingTask.disease_id == disease_id
                ).count()
                
                # Count arbitration pending tasks
                counts['arbitration_pending'] = db.query(GradingTask).filter(
                    GradingTask.state == 'arbitration',
                    GradingTask.lab_unit_id.in_(lab_unit_ids),
                    GradingTask.disease_id == disease_id
                ).count()
                
                kpi_data[disease_name] = counts
        else:
            # For regular users, only include diseases where they have eligibility
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
                    counts['arbitration_pending'] = db.query(GradingTask).filter(
                        GradingTask.state == 'arbitration',
                        GradingTask.lab_unit_id.in_(lab_unit_ids),
                        GradingTask.disease_id == disease_id
                    ).count()
                
                kpi_data[disease_name] = counts
        
        return kpi_data
    finally:
        db.close()


def get_all_pending_resident_for_disease(user_id: int, disease_id: int) -> Dict[str, int]:
    """
    Get total pending resident tasks for a user and disease across all eligible lab units.
    
    Args:
        user_id: The ID of the user
        disease_id: The ID of the disease
        
    Returns:
        A dictionary with 'total' (total count of pending tasks)
    """
    db = Session()
    try:
        # Check if user has resident role or is admin
        user = db.query(User).options(selectinload(User.roles)).filter(User.id == user_id).first()
        if not user:
            return {'total': 0}
            
        # Admins can see all tasks regardless of role
        is_admin = user.has_role('admin')
        if not is_admin and not user.has_role('resident'):
            return {'total': 0}
        
        # For admins, get all lab units for this disease
        if is_admin:
            lab_unit_ids = [lab_unit.id for lab_unit in db.query(LabUnit).all()]
        else:
            # Get all lab units where user is eligible for resident grading for this disease
            eligible_roles = db.query(UserDiseaseUnitRole).filter(
                UserDiseaseUnitRole.user_id == user_id,
                UserDiseaseUnitRole.disease_id == disease_id,
                UserDiseaseUnitRole.active == True,
                UserDiseaseUnitRole.can_grade_resident == True
            ).all()
            
            if not eligible_roles:
                return {'total': 0}
            
            lab_unit_ids = [role.lab_unit_id for role in eligible_roles]
        
        # Count pending tasks across all eligible lab units
        total = db.query(GradingTask).filter(
            GradingTask.state == 'pending',
            GradingTask.lab_unit_id.in_(lab_unit_ids),
            GradingTask.disease_id == disease_id
        ).count()
        
        return {'total': total}
    finally:
        db.close()


def get_all_pending_faculty_for_disease(user_id: int, disease_id: int) -> Dict[str, int]:
    """
    Get total pending faculty tasks for a user and disease across all eligible lab units.
    
    Args:
        user_id: The ID of the user
        disease_id: The ID of the disease
        
    Returns:
        A dictionary with 'total' (total count of pending tasks)
    """
    db = Session()
    try:
        # Check if user has faculty role (ophthalmologist) or is admin
        user = db.query(User).options(selectinload(User.roles)).filter(User.id == user_id).first()
        if not user:
            return {'total': 0}
            
        # Admins can see all tasks regardless of role
        is_admin = user.has_role('admin')
        if not is_admin and not user.has_role('ophthalmologist'):
            return {'total': 0}
        
        # For admins, get all lab units for this disease
        if is_admin:
            lab_unit_ids = [lab_unit.id for lab_unit in db.query(LabUnit).all()]
        else:
            # Get all lab units where user is eligible for faculty grading for this disease
            eligible_roles = db.query(UserDiseaseUnitRole).filter(
                UserDiseaseUnitRole.user_id == user_id,
                UserDiseaseUnitRole.disease_id == disease_id,
                UserDiseaseUnitRole.active == True,
                UserDiseaseUnitRole.can_grade_faculty == True
            ).all()
            
            if not eligible_roles:
                return {'total': 0}
            
            lab_unit_ids = [role.lab_unit_id for role in eligible_roles]
        
        # Count resident_done tasks across all eligible lab units
        total = db.query(GradingTask).filter(
            GradingTask.state == 'resident_done',
            GradingTask.lab_unit_id.in_(lab_unit_ids),
            GradingTask.disease_id == disease_id
        ).count()
        
        return {'total': total}
    finally:
        db.close()


def get_all_pending_arbitration_for_disease(user_id: int, disease_id: int) -> Dict[str, int]:
    """
    Get total pending arbitration tasks for a user and disease across all eligible lab units.
    
    Args:
        user_id: The ID of the user
        disease_id: The ID of the disease
        
    Returns:
        A dictionary with 'total' (total count of pending tasks)
    """
    db = Session()
    try:
        # Check if user has arbitration role (ophthalmologist) or is admin
        user = db.query(User).options(selectinload(User.roles)).filter(User.id == user_id).first()
        if not user:
            return {'total': 0}
            
        # Admins can see all tasks regardless of role
        is_admin = user.has_role('admin')
        if not is_admin and not user.has_role('ophthalmologist'):
            return {'total': 0}
        
        # For admins, get all lab units for this disease
        if is_admin:
            lab_unit_ids = [lab_unit.id for lab_unit in db.query(LabUnit).all()]
        else:
            # Get all lab units where user is eligible for arbitration for this disease
            eligible_roles = db.query(UserDiseaseUnitRole).filter(
                UserDiseaseUnitRole.user_id == user_id,
                UserDiseaseUnitRole.disease_id == disease_id,
                UserDiseaseUnitRole.active == True,
                UserDiseaseUnitRole.can_arbitrate == True
            ).all()
            
            if not eligible_roles:
                return {'total': 0}
            
            lab_unit_ids = [role.lab_unit_id for role in eligible_roles]
        
        # Count arbitration tasks across all eligible lab units
        total = db.query(GradingTask).filter(
            GradingTask.state == 'arbitration',
            GradingTask.lab_unit_id.in_(lab_unit_ids),
            GradingTask.disease_id == disease_id
        ).count()
        
        return {'total': total}
    finally:
        db.close()


def get_all_pending_resident_for_labUnit_disease(user_id: int, lab_unit_id: int, disease_id: int) -> Dict[str, Optional[int]]:
    """
    Get all pending resident tasks for a user, lab unit, and disease.
    
    Args:
        user_id: The ID of the user
        lab_unit_id: The ID of the lab unit
        disease_id: The ID of the disease
        
    Returns:
        A dictionary with 'total' (total count), 'first_task_id' (ID of first pending task),
        'first_task_img_uuid' (UUID of the image for the first task), and 
        'first_task_lab_unit_id' (lab unit ID of the first task)
    """
    db = Session()
    try:
        # Check if user has resident role for this lab unit and disease
        eligibility = db.query(UserDiseaseUnitRole).filter(
            UserDiseaseUnitRole.user_id == user_id,
            UserDiseaseUnitRole.disease_id == disease_id,
            UserDiseaseUnitRole.lab_unit_id == lab_unit_id,
            UserDiseaseUnitRole.active == True,
            UserDiseaseUnitRole.can_grade_resident == True
        ).first()
        
        if not eligibility:
            return {
                'total': 0,
                'first_task_id': None,
                'first_task_img_uuid': None,
                'first_task_lab_unit_id': None
            }
        
        query = db.query(GradingTask).options(
            selectinload(GradingTask.encounter_file),
            selectinload(GradingTask.direct_image)
        ).filter(
            GradingTask.state == 'pending',
            GradingTask.lab_unit_id == lab_unit_id,
            GradingTask.disease_id == disease_id
        )
        
        total = query.count()
        first_task = query.first()
        
        first_task_id = first_task.id if first_task else None
        first_task_img_uuid = None
        first_task_lab_unit_id = None
        
        if first_task:
            first_task_lab_unit_id = first_task.lab_unit_id
            if first_task.encounter_file:
                first_task_img_uuid = first_task.encounter_file.uuid
            elif first_task.direct_image:
                first_task_img_uuid = first_task.direct_image.uuid
        
        return {
            'total': total,
            'first_task_id': first_task_id,
            'first_task_img_uuid': first_task_img_uuid,
            'first_task_lab_unit_id': first_task_lab_unit_id
        }
    finally:
        db.close()


def get_all_pending_faculty_for_labUnit_disease(user_id: int, lab_unit_id: int, disease_id: int) -> Dict[str, Optional[int]]:
    """
    Get all pending faculty tasks for a user, lab unit, and disease.
    
    Args:
        user_id: The ID of the user
        lab_unit_id: The ID of the lab unit
        disease_id: The ID of the disease
        
    Returns:
        A dictionary with 'total' (total count), 'first_task_id' (ID of first pending task),
        'first_task_img_uuid' (UUID of the image for the first task), and 
        'first_task_lab_unit_id' (lab unit ID of the first task)
    """
    db = Session()
    try:
        # Check if user has faculty role for this lab unit and disease
        eligibility = db.query(UserDiseaseUnitRole).filter(
            UserDiseaseUnitRole.user_id == user_id,
            UserDiseaseUnitRole.disease_id == disease_id,
            UserDiseaseUnitRole.lab_unit_id == lab_unit_id,
            UserDiseaseUnitRole.active == True,
            UserDiseaseUnitRole.can_grade_faculty == True
        ).first()
        
        if not eligibility:
            return {
                'total': 0,
                'first_task_id': None,
                'first_task_img_uuid': None,
                'first_task_lab_unit_id': None
            }
        
        query = db.query(GradingTask).options(
            selectinload(GradingTask.encounter_file),
            selectinload(GradingTask.direct_image)
        ).filter(
            GradingTask.state == 'resident_done',
            GradingTask.lab_unit_id == lab_unit_id,
            GradingTask.disease_id == disease_id
        )
        
        total = query.count()
        first_task = query.first()
        
        first_task_id = first_task.id if first_task else None
        first_task_img_uuid = None
        first_task_lab_unit_id = None
        
        if first_task:
            first_task_lab_unit_id = first_task.lab_unit_id
            if first_task.encounter_file:
                first_task_img_uuid = first_task.encounter_file.uuid
            elif first_task.direct_image:
                first_task_img_uuid = first_task.direct_image.uuid
        
        return {
            'total': total,
            'first_task_id': first_task_id,
            'first_task_img_uuid': first_task_img_uuid,
            'first_task_lab_unit_id': first_task_lab_unit_id
        }
    finally:
        db.close()


def get_all_pending_arbitration_for_labUnit_disease(user_id: int, lab_unit_id: int, disease_id: int) -> Dict[str, Optional[int]]:
    """
    Get all pending arbitration tasks for a user, lab unit, and disease.
    
    Args:
        user_id: The ID of the user
        lab_unit_id: The ID of the lab unit
        disease_id: The ID of the disease
        
    Returns:
        A dictionary with 'total' (total count), 'first_task_id' (ID of first pending task),
        'first_task_img_uuid' (UUID of the image for the first task), and 
        'first_task_lab_unit_id' (lab unit ID of the first task)
    """
    db = Session()
    try:
        # Check if user has arbitration role for this lab unit and disease
        eligibility = db.query(UserDiseaseUnitRole).filter(
            UserDiseaseUnitRole.user_id == user_id,
            UserDiseaseUnitRole.disease_id == disease_id,
            UserDiseaseUnitRole.lab_unit_id == lab_unit_id,
            UserDiseaseUnitRole.active == True,
            UserDiseaseUnitRole.can_arbitrate == True
        ).first()
        
        if not eligibility:
            return {
                'total': 0,
                'first_task_id': None,
                'first_task_img_uuid': None,
                'first_task_lab_unit_id': None
            }
        
        query = db.query(GradingTask).options(
            selectinload(GradingTask.encounter_file),
            selectinload(GradingTask.direct_image)
        ).filter(
            GradingTask.state == 'arbitration',
            GradingTask.lab_unit_id == lab_unit_id,
            GradingTask.disease_id == disease_id
        )
        
        total = query.count()
        first_task = query.first()
        
        first_task_id = first_task.id if first_task else None
        first_task_img_uuid = None
        first_task_lab_unit_id = None
        
        if first_task:
            first_task_lab_unit_id = first_task.lab_unit_id
            if first_task.encounter_file:
                first_task_img_uuid = first_task.encounter_file.uuid
            elif first_task.direct_image:
                first_task_img_uuid = first_task.direct_image.uuid
        
        return {
            'total': total,
            'first_task_id': first_task_id,
            'first_task_img_uuid': first_task_img_uuid,
            'first_task_lab_unit_id': first_task_lab_unit_id
        }
    finally:
        db.close()


def get_user_eligibility_for_task(user_id: int, task_id: int, role_slot: str) -> bool:
    """
    Check if a user is eligible for a specific role slot for a task.
    
    Args:
        user_id: The ID of the user
        task_id: The ID of the task
        role_slot: The role slot ('resident', 'faculty', or 'arbitrator')
        
    Returns:
        True if user is eligible, False otherwise
    """
    db = Session()
    try:
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
            
        # Admins are eligible for all slots
        if user.has_role('admin'):
            return True
            
        # Check role requirements
        if role_slot == 'resident' and not user.has_role('resident'):
            return False
        elif role_slot in ('faculty', 'arbitrator') and not user.has_role('ophthalmologist'):
            return False
            
        # Check eligibility matrix using UserDiseaseUnitRole table
        eligibility_filter = None
        if role_slot == 'resident':
            eligibility_filter = UserDiseaseUnitRole.can_grade_resident == True
        elif role_slot == 'faculty':
            eligibility_filter = UserDiseaseUnitRole.can_grade_faculty == True
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
    finally:
        db.close()


def get_next_eligible_task(user_id: int, role_slot: str, lab_unit_id: Optional[int] = None, disease_id: Optional[int] = None) -> Optional[GradingTask]:
    """
    Get the next eligible task for a user and role slot.
    
    Args:
        user_id: The ID of the user
        role_slot: The role slot ('resident', 'faculty', or 'arbitrator')
        lab_unit_id: Optional lab unit ID to filter by
        disease_id: Optional disease ID to filter by
        
    Returns:
        The next eligible GradingTask or None if no tasks are available
    """
    db = Session()
    try:
        # Load user
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return None
            
        # Build query for next task
        query = db.query(GradingTask)
        
        # Filter by lab unit if specified
        if lab_unit_id:
            query = query.filter(GradingTask.lab_unit_id == lab_unit_id)
            
        # Filter by disease if specified
        if disease_id:
            query = query.filter(GradingTask.disease_id == disease_id)
            
        # Filter by role-specific states
        if role_slot == "arbitrator":
            # Arbitrators only see arbitration tasks
            query = query.filter(GradingTask.state == "arbitration")
        elif role_slot == "resident":
            # Residents see pending tasks
            query = query.filter(GradingTask.state == "pending")
        elif role_slot == "faculty":
            # Faculty see tasks where resident has completed grading
            query = query.filter(GradingTask.state == "resident_done")
            
        # Exclude tasks already graded by this user for this role
        # This would require checking the Grade table
        # For now, we'll just return the first available task
        
        return query.first()
    finally:
        db.close()


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
    from models import Grade  # Import here to avoid circular imports
    
    db = Session()
    try:
        # Get user with roles
        user = db.query(User).options(selectinload(User.roles)).filter(User.id == user_id).first()
        if not user:
            return {}
        
        # Check if user is admin
        is_admin = user.has_role('admin')
        
        # Get all diseases
        diseases = db.query(Disease).all()
        disease_names = {disease.id: disease.name for disease in diseases}
        
        # For admins, get all lab units; for regular users, get only eligible lab units
        if is_admin:
            all_lab_unit_ids = [lab_unit.id for lab_unit in db.query(LabUnit).all()]
        
        # Get user's eligible roles
        if is_admin:
            # Admins can see all diseases and lab units
            eligible_roles = db.query(UserDiseaseUnitRole).filter(
                UserDiseaseUnitRole.active == True
            ).all()
        else:
            eligible_roles = db.query(UserDiseaseUnitRole).filter(
                UserDiseaseUnitRole.user_id == user_id,
                UserDiseaseUnitRole.active == True
            ).all()
        
        if not eligible_roles and not is_admin:
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
        
        # Calculate task counts for each disease based on completed gradings
        kpi_data = {}
        
        # For admins, include all diseases even if they have no explicit eligibility
        if is_admin:
            for disease_id, disease_name in disease_names.items():
                lab_unit_ids = all_lab_unit_ids
                
                counts = {
                    'resident_completed': 0,
                    'faculty_completed': 0,
                    'arbitration_completed': 0
                }
                
                # Count resident completed tasks (resident gradings)
                counts['resident_completed'] = db.query(Grade).filter(
                    Grade.grader_user_id == user_id,
                    Grade.role_slot == 'resident',
                    Grade.task.has(lab_unit_id.in_(lab_unit_ids)),
                    Grade.task.has(disease_id == disease_id)
                ).count()
                
                # Count faculty completed tasks (faculty gradings)
                counts['faculty_completed'] = db.query(Grade).filter(
                    Grade.grader_user_id == user_id,
                    Grade.role_slot == 'faculty',
                    Grade.task.has(lab_unit_id.in_(lab_unit_ids)),
                    Grade.task.has(disease_id == disease_id)
                ).count()
                
                # Count arbitration completed tasks (arbitrator gradings)
                counts['arbitration_completed'] = db.query(Grade).filter(
                    Grade.grader_user_id == user_id,
                    Grade.role_slot == 'arbitrator',
                    Grade.task.has(lab_unit_id.in_(lab_unit_ids)),
                    Grade.task.has(disease_id == disease_id)
                ).count()
                
                kpi_data[disease_name] = counts
        else:
            # For regular users, only include diseases where they have eligibility
            for disease_id, info in disease_lab_units.items():
                disease_name = disease_names.get(disease_id, f"Unknown Disease {disease_id}")
                lab_unit_ids = list(info['lab_units'])
                
                counts = {
                    'resident_completed': 0,
                    'faculty_completed': 0,
                    'arbitration_completed': 0
                }
                
                # Check if user has the required roles
                has_resident_role = user.has_role('resident')
                has_faculty_role = user.has_role('ophthalmologist')
                
                # Count resident completed tasks (only if user is resident and has resident eligibility)
                if has_resident_role and info['can_grade_resident']:
                    counts['resident_completed'] = db.query(Grade).filter(
                        Grade.grader_user_id == user_id,
                        Grade.role_slot == 'resident',
                        Grade.task.has(lab_unit_id.in_(lab_unit_ids)),
                        Grade.task.has(disease_id == disease_id)
                    ).count()
                
                # Count faculty completed tasks (only if user is faculty and has faculty eligibility)
                if has_faculty_role and info['can_grade_faculty']:
                    counts['faculty_completed'] = db.query(Grade).filter(
                        Grade.grader_user_id == user_id,
                        Grade.role_slot == 'faculty',
                        Grade.task.has(lab_unit_id.in_(lab_unit_ids)),
                        Grade.task.has(disease_id == disease_id)
                    ).count()
                
                # Count arbitration completed tasks (only if user is faculty and has arbitration eligibility)
                if has_faculty_role and info['can_arbitrate']:
                    counts['arbitration_completed'] = db.query(Grade).filter(
                        Grade.grader_user_id == user_id,
                        Grade.role_slot == 'arbitrator',
                        Grade.task.has(lab_unit_id.in_(lab_unit_ids)),
                        Grade.task.has(disease_id == disease_id)
                    ).count()
                
                kpi_data[disease_name] = counts
        
        return kpi_data
    finally:
        db.close()