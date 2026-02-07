"""
Utility functions for dual grading operations.

Note: All functions in this module expect a database session to be passed as a parameter.
The caller is responsible for managing the session lifecycle (opening and closing).
This design allows for better transaction management and session reuse.
"""

from sqlalchemy.orm import selectinload, aliased
from sqlalchemy import and_, or_, func, exists
from models import GradingTask, User, UserDiseaseUnitRole, EncounterFile, DirectImageUpload, Disease, LabUnit, Grade, DiseaseGrading, LinkedDiseaseGrading
from utils.hospital_scoping import apply_scoping
from utils.linkedGradingUtils import get_linked_disease_ids, get_primary_disease_id
from typing import Dict, Optional, List, Tuple


def _apply_linked_mismatch_exclusion(db, query, disease_id: int):
    linked_ids = get_linked_disease_ids(db, disease_id)
    if not linked_ids:
        return query

    LinkedTask = aliased(GradingTask)
    image_match = or_(
        and_(
            GradingTask.encounter_file_id.isnot(None),
            GradingTask.encounter_file_id == LinkedTask.encounter_file_id,
        ),
        and_(
            GradingTask.direct_image_upload_id.isnot(None),
            GradingTask.direct_image_upload_id == LinkedTask.direct_image_upload_id,
        ),
        and_(
            GradingTask.patient_encounter_id.isnot(None),
            GradingTask.patient_encounter_id == LinkedTask.patient_encounter_id,
        ),
    )
    mismatch_filter = or_(
        and_(GradingTask.state == "resident_done", LinkedTask.state == "pending"),
        and_(
            GradingTask.state.in_(["resident2_done", "final"]),
            LinkedTask.state == "resident_done",
        ),
    )
    mismatch_exists = (
        exists()
        .select_from(LinkedTask)
        .where(image_match)
        .where(LinkedTask.disease_id.in_(linked_ids))
        .where(
            and_(
                LinkedDiseaseGrading.primary_disease_id == GradingTask.disease_id,
                LinkedDiseaseGrading.linked_disease_id == LinkedTask.disease_id,
                LinkedDiseaseGrading.is_active.is_(True),
            )
        )
        .where(mismatch_filter)
    )
    return query.filter(~mismatch_exists)


def get_user_kpi_pending_task_count_data(db, user_id: int) -> Dict[str, Dict[str, int]]:
    """
    Get KPI data for each core disease for pending tasks across all mapped lab units for each slot of a user.
    
    This function provides a comprehensive view of pending tasks by disease for all eligible slots
    (resident, resident2, arbitration) across all lab units where the user has eligibility.
    
    Args:
        db: Database session (caller is responsible for closing)
        user_id: The ID of the user
        
    Returns:
        A dictionary with disease names as keys and slot counts as values:
        {
            'Disease Name': {
                'resident_pending': count,
                'resident2_pending': count,
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
    
    # Group eligible lab units by disease, including linked diseases from primary permissions
    disease_lab_units = {}
    for role in eligible_roles:
        primary_id = role.disease_id
        linked_ids = get_linked_disease_ids(db, primary_id)
        all_ids = [primary_id] + linked_ids
        for disease_id in all_ids:
            is_currently_primary = (disease_id == primary_id)
            if disease_id not in disease_lab_units:
                disease_lab_units[disease_id] = {
                    'lab_units': set(),
                    'can_grade_resident': False,
                    'can_grade_resident2': False,
                    'can_arbitrate': False,
                    'is_linked_only': not is_currently_primary,
                }
            else:
                if is_currently_primary:
                    disease_lab_units[disease_id]['is_linked_only'] = False
            
            disease_lab_units[disease_id]['lab_units'].add(role.lab_unit_id)
            disease_lab_units[disease_id]['can_grade_resident'] |= role.can_grade_resident
            disease_lab_units[disease_id]['can_grade_resident2'] |= role.can_grade_resident2
            disease_lab_units[disease_id]['can_arbitrate'] |= role.can_arbitrate
    
    # Calculate task counts for each disease
    kpi_data = {}
    
    # For all users (including admins), only include diseases where they have eligibility
    for disease_id, info in disease_lab_units.items():
        # Skip diseases that are only linked to others; they are discoverable via their primary disease
        if info.get('is_linked_only'):
            continue
            
        disease_name = disease_names.get(disease_id, f"Unknown Disease {disease_id}")
        lab_unit_ids = list(info['lab_units'])
        
        counts = {
            'resident_pending': 0,
            'resident2_pending': 0,
            'arbitration_pending': 0
        }
        
        # Check if user has the required roles
        has_resident_role = user.has_role('resident')
        has_resident2_role = user.has_role('ophthalmologist')
        
        # Count resident pending tasks (skip linked diseases: graded with primary)
        if (has_resident_role or has_resident2_role) and info['can_grade_resident']:
            # Exclude tasks that the user has already graded as a resident
            q = db.query(GradingTask).filter(
                GradingTask.state == 'pending',
                GradingTask.lab_unit_id.in_(lab_unit_ids),
                GradingTask.disease_id == disease_id,
                ~GradingTask.grades.any(
                    and_(
                        Grade.grader_user_id == user_id,
                        Grade.role_slot == 'resident'
                    )
                )
            )
            q = _apply_linked_mismatch_exclusion(db, q, disease_id)
            q = apply_scoping(q, GradingTask, user, 'grading')
            counts['resident_pending'] = q.count()
        
        # Count resident2 pending tasks (skip linked diseases: graded with primary)
        if (has_resident_role or has_resident2_role) and (info['can_grade_resident2'] or info['can_grade_resident']):
            # Exclude tasks that the user has already graded in either resident slot
            q = db.query(GradingTask).filter(
                GradingTask.state == 'resident_done',
                GradingTask.lab_unit_id.in_(lab_unit_ids),
                GradingTask.disease_id == disease_id,
                ~GradingTask.grades.any(
                    and_(
                        Grade.grader_user_id == user_id,
                        Grade.role_slot.in_(('resident', 'resident2'))
                    )
                )
            )
            q = _apply_linked_mismatch_exclusion(db, q, disease_id)
            q = apply_scoping(q, GradingTask, user, 'grading')
            counts['resident2_pending'] = q.count()
        
        # Count arbitration pending tasks (only if user has resident2 eligibility and arbitration permissions)
        if has_resident2_role and info['can_arbitrate']:
            # Base query for the current disease
            base_q = db.query(GradingTask).filter(
                GradingTask.lab_unit_id.in_(lab_unit_ids),
                GradingTask.disease_id == disease_id
            )

            # Check if we should include linked tasks in arbitration
            linked_ids = []
            if not info.get('is_linked_only'):
                linked_ids = get_linked_disease_ids(db, disease_id)

            if linked_ids:
                LinkedTask = aliased(GradingTask)
                # Outer join to find any linked task that is in arbitration
                base_q = base_q.outerjoin(
                    LinkedTask,
                    and_(
                        or_(
                            and_(GradingTask.encounter_file_id != None, GradingTask.encounter_file_id == LinkedTask.encounter_file_id),
                            and_(GradingTask.direct_image_upload_id != None, GradingTask.direct_image_upload_id == LinkedTask.direct_image_upload_id)
                        ),
                        LinkedTask.disease_id.in_(linked_ids)
                    )
                ).filter(
                    or_(
                        GradingTask.state == 'arbitration',
                        LinkedTask.state == 'arbitration'
                    )
                )
            else:
                base_q = base_q.filter(GradingTask.state == 'arbitration')

            q = apply_scoping(base_q, GradingTask, user, 'grading')
            
            # Use distinct because the join might produce multiple rows per primary task
            arbitration_tasks = q.distinct().all()
            
            # Apply same filtering as in task assignment to exclude tasks user recently graded
            from utils.dualGradingGetNextTasks import _has_user_graded_task_2weeks
            eligible_arbitration_tasks = []
            for task in arbitration_tasks:
                if not _has_user_graded_task_2weeks(db, user_id, task.id):
                    eligible_arbitration_tasks.append(task)
            
            counts['arbitration_pending'] = len(eligible_arbitration_tasks)
            counts['arbitration_breakdown'] = {}

            # Calculate breakdown of which diseases are actually in arbitration
            if eligible_arbitration_tasks:
                # 1. Primary Disease Counts
                primary_count = sum(1 for t in eligible_arbitration_tasks if t.state == 'arbitration')
                if primary_count > 0:
                    counts['arbitration_breakdown'][disease_name] = primary_count
                
                # 2. Linked Disease Counts
                if linked_ids:
                    # Collect file/upload IDs from eligible tasks to scope the query
                    file_ids = [t.encounter_file_id for t in eligible_arbitration_tasks if t.encounter_file_id]
                    upload_ids = [t.direct_image_upload_id for t in eligible_arbitration_tasks if t.direct_image_upload_id]
                    
                    filters = []
                    if file_ids:
                        filters.append(GradingTask.encounter_file_id.in_(file_ids))
                    if upload_ids:
                        filters.append(GradingTask.direct_image_upload_id.in_(upload_ids))
                    
                    if filters:
                        linked_counts = db.query(
                            GradingTask.disease_id, 
                            func.count(GradingTask.id)
                        ).filter(
                            GradingTask.disease_id.in_(linked_ids),
                            GradingTask.state == 'arbitration',
                            or_(*filters)
                        ).group_by(GradingTask.disease_id).all()
                        
                        for did, count in linked_counts:
                            dname = disease_names.get(did)
                            if dname:
                                counts['arbitration_breakdown'][dname] = count
        
        kpi_data[disease_name] = counts
    
    return kpi_data


def get_user_kpi_completed_task_count_data(db, user_id: int) -> Dict[str, Dict[str, int]]:
    """
    Get KPI data for each core disease for completed tasks across all mapped lab units for each slot of a user.
    
    This function provides a comprehensive view of completed tasks by disease for all eligible slots
    (resident, resident2, arbitration) across all lab units where the user has eligibility.
    
    Args:
        db: Database session (caller is responsible for closing)
        user_id: The ID of the user
        
    Returns:
        A dictionary with disease names as keys and slot counts as values:
        {
            'Disease Name': {
                'resident_completed': count,
                'resident2_completed': count,
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
    has_resident2_role = user.has_role('ophthalmologist')
    
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
        is_linked = get_primary_disease_id(db, disease_id) != disease_id
        if is_linked:
            continue
            
        disease_name = disease_names.get(disease_id, f"Unknown Disease {disease_id}")
        
        counts = {
            'resident_completed': 0,
            'resident2_completed': 0,
            'arbitration_completed': 0
        }
        
        # Count resident completed tasks
        # Allow both residents and resident2 graders to count resident completed tasks
        if (has_resident_role or has_resident2_role) and not is_linked:
            q = db.query(Grade).filter(
                Grade.grader_user_id == user_id,
                Grade.role_slot == 'resident',
                Grade.task.has(GradingTask.disease_id == disease_id)
            )
            q = apply_scoping(q, Grade, user, 'grading')
            counts['resident_completed'] = q.count()
        
        # Count resident2 completed tasks
        if has_resident2_role:
            q = db.query(Grade).filter(
                Grade.grader_user_id == user_id,
                Grade.role_slot == 'resident2',
                Grade.task.has(GradingTask.disease_id == disease_id)
            )
            q = apply_scoping(q, Grade, user, 'grading')
            counts['resident2_completed'] = q.count()
    
        # Count arbitration completed tasks
        if has_resident2_role:
            q = db.query(Grade).filter(
                Grade.grader_user_id == user_id,
                Grade.role_slot == 'arbitrator',
                Grade.task.has(GradingTask.disease_id == disease_id)
            )
            q = apply_scoping(q, Grade, user, 'grading')
            counts['arbitration_completed'] = q.count()
        
        kpi_data[disease_name] = counts
    
    return kpi_data


def get_user_kpi_linked_followup_counts(db, user_id: int) -> Dict[str, List[Dict[str, int | str]]]:
    """
    Get counts of linked-task state mismatches by primary disease and linked disease.
    Combines resident and resident2 follow-up conditions.
    """
    user = db.query(User).options(selectinload(User.roles)).filter(User.id == user_id).first()
    if not user:
        return {}

    has_resident_role = user.has_role('resident')
    has_resident2_role = user.has_role('ophthalmologist')
    if not (has_resident_role or has_resident2_role):
        return {}

    diseases = db.query(Disease).all()
    disease_names = {disease.id: disease.name for disease in diseases}

    eligible_roles = db.query(UserDiseaseUnitRole).filter(
        UserDiseaseUnitRole.user_id == user_id,
        UserDiseaseUnitRole.active == True
    ).all()
    if not eligible_roles:
        return {}

    disease_lab_units = {}
    for role in eligible_roles:
        primary_id = role.disease_id
        linked_ids = get_linked_disease_ids(db, primary_id)
        all_ids = [primary_id] + linked_ids
        for disease_id in all_ids:
            is_currently_primary = (disease_id == primary_id)
            if disease_id not in disease_lab_units:
                disease_lab_units[disease_id] = {
                    'lab_units': set(),
                    'can_grade_resident': False,
                    'can_grade_resident2': False,
                    'is_linked_only': not is_currently_primary,
                }
            else:
                if is_currently_primary:
                    disease_lab_units[disease_id]['is_linked_only'] = False

            disease_lab_units[disease_id]['lab_units'].add(role.lab_unit_id)
            disease_lab_units[disease_id]['can_grade_resident'] |= role.can_grade_resident
            disease_lab_units[disease_id]['can_grade_resident2'] |= role.can_grade_resident2

    results: Dict[str, List[Dict[str, int | str]]] = {}

    for disease_id, info in disease_lab_units.items():
        if info.get('is_linked_only'):
            continue

        if not (info['can_grade_resident'] or info['can_grade_resident2']):
            continue

        disease_name = disease_names.get(disease_id, f"Unknown Disease {disease_id}")
        lab_unit_ids = list(info['lab_units'])
        if not lab_unit_ids:
            continue

        PrimaryTask = aliased(GradingTask)
        LinkedTask = aliased(GradingTask)
        LinkedDisease = aliased(Disease)

        image_match = or_(
            and_(
                PrimaryTask.encounter_file_id.isnot(None),
                PrimaryTask.encounter_file_id == LinkedTask.encounter_file_id,
            ),
            and_(
                PrimaryTask.direct_image_upload_id.isnot(None),
                PrimaryTask.direct_image_upload_id == LinkedTask.direct_image_upload_id,
            ),
            and_(
                PrimaryTask.patient_encounter_id.isnot(None),
                PrimaryTask.patient_encounter_id == LinkedTask.patient_encounter_id,
            ),
        )
        mismatch_filter = or_(
            and_(PrimaryTask.state == "resident_done", LinkedTask.state == "pending"),
            and_(
                PrimaryTask.state.in_(["resident2_done", "final"]),
                LinkedTask.state == "resident_done",
            ),
        )

        q = (
            db.query(LinkedDisease.id, LinkedDisease.name, func.count(func.distinct(PrimaryTask.id)))
            .select_from(PrimaryTask)
            .join(LinkedTask, image_match)
            .join(
                LinkedDiseaseGrading,
                and_(
                    LinkedDiseaseGrading.primary_disease_id == PrimaryTask.disease_id,
                    LinkedDiseaseGrading.linked_disease_id == LinkedTask.disease_id,
                    LinkedDiseaseGrading.is_active.is_(True),
                ),
            )
            .join(LinkedDisease, LinkedDisease.id == LinkedTask.disease_id)
            .filter(PrimaryTask.disease_id == disease_id)
            .filter(PrimaryTask.lab_unit_id.in_(lab_unit_ids))
            .filter(mismatch_filter)
            .group_by(LinkedDisease.id, LinkedDisease.name)
        )

        q = apply_scoping(q, PrimaryTask, user, 'grading')
        rows = q.all()
        if rows:
            results[disease_name] = [
                {"id": row[0], "name": row[1], "count": row[2]}
                for row in rows
            ]

    return results
