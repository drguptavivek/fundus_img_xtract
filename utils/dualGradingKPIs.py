"""
Utility functions for dual grading operations.

Note: All functions in this module expect a database session to be passed as a parameter.
The caller is responsible for managing the session lifecycle (opening and closing).
This design allows for better transaction management and session reuse.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import selectinload, aliased
from sqlalchemy import and_, or_, func, exists, case, select
from models import (
    DirectImageUpload,
    Disease,
    DiseaseGrading,
    EncounterFile,
    EncounterSetImage,
    Grade,
    GradingTask,
    LabUnit,
    LinkedDiseaseGrading,
    User,
    UserDiseaseUnitRole,
)
from grading_allocation.eligibility import eligible_enforced_project_task_contexts
from grading_allocation.exceptions import AllocationContextError
from grading_allocation.models import ProjectGradingAllocationPolicy
from grading_allocation.resolver import resolve_task_allocation_context
from grading.workbench.models import GradingWorkbenchSession, GradingWorkbenchSessionTarget
from utils.linkedGradingUtils import get_linked_disease_ids, get_primary_disease_id
from utils.dualGradingEligibility import _has_user_graded_task_4weeks
from grading_allocation.dashboard import (
    exclude_enforced_project_encounter_set_tasks,
    exclude_unallocated_project_tasks,
)
from typing import Dict, Optional, List, Tuple


def _active_workbench_lease_exists(db, task_entity, role_slot: str):
    return (
        db.query(GradingWorkbenchSessionTarget.id)
        .join(GradingWorkbenchSession)
        .filter(
            GradingWorkbenchSessionTarget.task_id == task_entity.id,
            GradingWorkbenchSessionTarget.role_slot == role_slot,
            GradingWorkbenchSessionTarget.target_purpose == "editable",
            GradingWorkbenchSessionTarget.released_at.is_(None),
            GradingWorkbenchSession.status == "active",
        )
    )


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
        and_(
            GradingTask.encounter_set_image_id.isnot(None),
            GradingTask.encounter_set_image_id == LinkedTask.encounter_set_image_id,
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


def _eligible_pending_tasks(
    db,
    query,
    *,
    user_id: int,
    role_slot: str,
    enforced_project_ids: set[int],
):
    """Apply authoritative allocation eligibility to mixed legacy KPI candidates."""
    tasks = (
        query.distinct()
        .options(
            selectinload(GradingTask.encounter_file).selectinload(
                EncounterFile.patient_encounter
            ),
            selectinload(GradingTask.direct_image),
            selectinload(GradingTask.patient_encounter),
            selectinload(GradingTask.encounter_set_image).selectinload(
                EncounterSetImage.patient_encounter
            ),
            selectinload(GradingTask.encounter_set_package),
        )
        .all()
    )
    if not tasks or not enforced_project_ids:
        return tasks
    eligible_contexts = eligible_enforced_project_task_contexts(
        db,
        user_id=user_id,
        task_slots=[(task, role_slot) for task in tasks],
        enforced_project_ids=enforced_project_ids,
    )
    eligible_tasks = []
    for task in tasks:
        try:
            context = resolve_task_allocation_context(db, task)
        except AllocationContextError:
            continue
        if context.project_id in enforced_project_ids:
            if (task.id, role_slot) in eligible_contexts:
                eligible_tasks.append(task)
        else:
            eligible_tasks.append(task)
    return eligible_tasks


def _pending_count(
    db,
    query,
    *,
    user_id: int,
    role_slot: str,
    enforced_project_ids: set[int],
) -> int:
    if not enforced_project_ids:
        return query.count()
    return len(
        _eligible_pending_tasks(
            db,
            query,
            user_id=user_id,
            role_slot=role_slot,
            enforced_project_ids=enforced_project_ids,
        )
    )


def get_user_kpi_pending_task_count_data(
    db,
    user_id: int,
    *,
    exclude_enforced_project_encounter_sets: bool = False,
) -> Dict[str, Dict[str, int]]:
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

    enforced_project_ids = (
        set(
            db.execute(
                select(ProjectGradingAllocationPolicy.project_id).where(
                    ProjectGradingAllocationPolicy.enforcement_enabled.is_(True)
                )
            ).scalars()
        )
        if exclude_enforced_project_encounter_sets
        else set()
    )
    
    # Group eligible lab units by disease, including linked diseases from primary permissions
    disease_lab_units = {}
    for role in eligible_roles:
        primary_id = get_primary_disease_id(db, role.disease_id)
        if role.disease_id != primary_id:
            continue
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
        has_resident2_role = user.has_role('ophthalmologist')
        
        # Count resident pending tasks (skip linked diseases: graded with primary)
        if has_resident2_role and info['can_grade_resident']:
            resident_tracker_exists = _active_workbench_lease_exists(
                db, GradingTask, "resident"
            )
            resident_conflict_exists = (
                db.query(Grade.id)
                .filter(
                    Grade.task_id == GradingTask.id,
                    Grade.grader_user_id == user_id,
                    Grade.role_slot.in_(("resident2",)),
                )
            )
            # Base resident queue (state=pending)
            q = db.query(GradingTask).filter(
                GradingTask.state == 'pending',
                GradingTask.lab_unit_id.in_(lab_unit_ids),
                GradingTask.disease_id == disease_id,
                ~resident_tracker_exists.exists(),
                ~resident_conflict_exists.exists(),
            )
            q = _apply_linked_mismatch_exclusion(db, q, disease_id)
            if exclude_enforced_project_encounter_sets:
                q = exclude_enforced_project_encounter_set_tasks(q)
            q = exclude_unallocated_project_tasks(
                q, user_id=user_id, capacity="resident", disease_id=disease_id
            )
            resident_pending_count = _pending_count(
                db,
                q,
                user_id=user_id,
                role_slot="resident",
                enforced_project_ids=enforced_project_ids,
            )

            # Include inconsistent resident tasks that are assignable by resident slot
            resident2_exists = (
                db.query(Grade.id)
                .filter(and_(Grade.task_id == GradingTask.id, Grade.role_slot == "resident2"))
            )
            resident_missing = ~exists().where(and_(Grade.task_id == GradingTask.id, Grade.role_slot == "resident"))

            inconsistent_q = db.query(GradingTask).filter(
                GradingTask.state == 'resident2_done',
                GradingTask.lab_unit_id.in_(lab_unit_ids),
                GradingTask.disease_id == disease_id,
                resident_missing,
                resident2_exists.exists(),
                ~resident_tracker_exists.exists(),
                ~resident_conflict_exists.exists(),
            )
            if exclude_enforced_project_encounter_sets:
                inconsistent_q = exclude_enforced_project_encounter_set_tasks(
                    inconsistent_q
                )
            inconsistent_q = exclude_unallocated_project_tasks(
                inconsistent_q, user_id=user_id, capacity="resident", disease_id=disease_id
            )
            inconsistent_count = _pending_count(
                db,
                inconsistent_q,
                user_id=user_id,
                role_slot="resident",
                enforced_project_ids=enforced_project_ids,
            )

            counts['resident_pending'] = resident_pending_count + inconsistent_count
        
        # Count resident2 pending tasks (skip linked diseases: graded with primary)
        if has_resident2_role and (info['can_grade_resident2'] or info['can_grade_resident']):
            resident2_tracker_exists = _active_workbench_lease_exists(
                db, GradingTask, "resident2"
            )
            resident2_conflict_exists = (
                db.query(Grade.id)
                .filter(
                    Grade.task_id == GradingTask.id,
                    Grade.grader_user_id == user_id,
                    Grade.role_slot.in_(("resident",)),
                )
            )
            q = db.query(GradingTask).filter(
                GradingTask.state == 'resident_done',
                GradingTask.lab_unit_id.in_(lab_unit_ids),
                GradingTask.disease_id == disease_id,
                ~resident2_tracker_exists.exists(),
                ~resident2_conflict_exists.exists(),
            )
            q = _apply_linked_mismatch_exclusion(db, q, disease_id)
            if exclude_enforced_project_encounter_sets:
                q = exclude_enforced_project_encounter_set_tasks(q)
            q = exclude_unallocated_project_tasks(
                q, user_id=user_id, capacity="resident", disease_id=disease_id
            )
            counts['resident2_pending'] = _pending_count(
                db,
                q,
                user_id=user_id,
                role_slot="resident2",
                enforced_project_ids=enforced_project_ids,
            )
        
        # Count arbitration pending tasks (only if user has resident2 eligibility and arbitration permissions)
        if has_resident2_role and info['can_arbitrate']:
            arbitration_tracker_exists = _active_workbench_lease_exists(
                db, GradingTask, "arbitrator"
            )
            # Base query for the current disease
            base_q = db.query(GradingTask).filter(
                GradingTask.lab_unit_id.in_(lab_unit_ids),
                GradingTask.disease_id == disease_id,
                ~arbitration_tracker_exists.exists(),
            )

            # Check if we should include linked tasks in arbitration
            linked_ids = []
            if not info.get('is_linked_only'):
                linked_ids = get_linked_disease_ids(db, disease_id)

            if linked_ids:
                LinkedTask = aliased(GradingTask)
                primary_tracker_exists = _active_workbench_lease_exists(
                    db, GradingTask, "arbitrator"
                )
                linked_tracker_exists = _active_workbench_lease_exists(
                    db, LinkedTask, "arbitrator"
                )
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
                        and_(GradingTask.state == 'arbitration', ~primary_tracker_exists.exists()),
                        and_(LinkedTask.state == 'arbitration', ~linked_tracker_exists.exists()),
                    )
                )
            else:
                base_q = base_q.filter(GradingTask.state == 'arbitration')

            if exclude_enforced_project_encounter_sets:
                base_q = exclude_enforced_project_encounter_set_tasks(base_q)
            q = exclude_unallocated_project_tasks(
                base_q, user_id=user_id, capacity="arbitrator", disease_id=disease_id
            )
            
            # Use distinct because the join might produce multiple rows per primary task
            if enforced_project_ids:
                eligible_arbitration_rows = _eligible_pending_tasks(
                    db,
                    q,
                    user_id=user_id,
                    role_slot="arbitrator",
                    enforced_project_ids=enforced_project_ids,
                )
            else:
                eligible_arbitration_rows = (
                    q.with_entities(
                        GradingTask.id,
                        GradingTask.state,
                        GradingTask.encounter_file_id,
                        GradingTask.direct_image_upload_id,
                    )
                    .distinct()
                    .all()
                )

            counts['arbitration_pending'] = len(eligible_arbitration_rows)
            counts['arbitration_breakdown'] = {}

            # Calculate breakdown of which diseases are actually in arbitration
            if eligible_arbitration_rows:
                # 1. Primary Disease Counts
                primary_count = sum(1 for t in eligible_arbitration_rows if t.state == 'arbitration')
                if primary_count > 0:
                    counts['arbitration_breakdown'][disease_name] = primary_count
                
                # 2. Linked Disease Counts
                if linked_ids:
                    # Collect file/upload IDs from eligible tasks to scope the query
                    file_ids = [t.encounter_file_id for t in eligible_arbitration_rows if t.encounter_file_id]
                    upload_ids = [t.direct_image_upload_id for t in eligible_arbitration_rows if t.direct_image_upload_id]
                    
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
            counts['resident_completed'] = q.count()
        
        # Count resident2 completed tasks
        if has_resident2_role:
            q = db.query(Grade).filter(
                Grade.grader_user_id == user_id,
                Grade.role_slot == 'resident2',
                Grade.task.has(GradingTask.disease_id == disease_id)
            )
            counts['resident2_completed'] = q.count()
    
        # Count arbitration completed tasks
        if has_resident2_role:
            q = db.query(Grade).filter(
                Grade.grader_user_id == user_id,
                Grade.role_slot == 'arbitrator',
                Grade.task.has(GradingTask.disease_id == disease_id)
            )
            counts['arbitration_completed'] = q.count()
        
        kpi_data[disease_name] = counts
    
    return kpi_data


def get_user_task_tracker_kpi_data(
    db,
    user_id: int,
    *,
    stuck_after_minutes: int = 60,
) -> Dict[str, object]:
    """Summarize durable workbench sessions currently held by a user."""
    now = datetime.now(timezone.utc)
    sessions = (
        db.query(GradingWorkbenchSession)
        .filter(
            GradingWorkbenchSession.user_id == user_id,
            GradingWorkbenchSession.status == "active",
        )
        .all()
    )

    by_role = {
        "resident": 0,
        "resident2": 0,
        "arbitrator": 0,
    }
    stale_by_role = {
        "resident": 0,
        "resident2": 0,
        "arbitrator": 0,
    }

    active_count = 0
    stale_count = 0

    for session in sessions:
        role = session.role_slot
        if role in by_role:
            by_role[role] += 1

        idle_expiry = session.idle_expires_at
        absolute_expiry = session.absolute_expires_at
        if idle_expiry and idle_expiry.tzinfo is None:
            idle_expiry = idle_expiry.replace(tzinfo=timezone.utc)
        if absolute_expiry and absolute_expiry.tzinfo is None:
            absolute_expiry = absolute_expiry.replace(tzinfo=timezone.utc)
        is_stale = bool(idle_expiry <= now or absolute_expiry <= now)
        if is_stale:
            stale_count += 1
            if role in stale_by_role:
                stale_by_role[role] += 1
        else:
            active_count += 1

    latest_session = max(sessions, key=lambda item: item.acquired_at, default=None)

    resume_task = None
    if latest_session:
        first_target = min(latest_session.targets, key=lambda item: item.target_order, default=None)
        task = db.get(GradingTask, first_target.task_id) if first_target else None
        resume_task = {
            "session_uuid": latest_session.uuid,
            "task_uuid": task.uuid if task else None,
            "slot_type": latest_session.role_slot,
            "disease_name": task.disease.name if task and task.disease else "Grading",
            "is_stale": bool(
                latest_session.idle_expires_at <= now
                or latest_session.absolute_expires_at <= now
            ),
        }

    return {
        "total": len(sessions),
        "active": active_count,
        "stale": stale_count,
        "by_role": by_role,
        "stale_by_role": stale_by_role,
        "stuck_after_minutes": stuck_after_minutes,
        "resume_task": resume_task,
    }


def get_user_kpi_linked_followup_counts(
    db,
    user_id: int,
    *,
    exclude_enforced_project_encounter_sets: bool = False,
) -> Dict[str, List[Dict[str, int | str]]]:
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
        primary_id = get_primary_disease_id(db, role.disease_id)
        if role.disease_id != primary_id:
            continue
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

        q = exclude_unallocated_project_tasks(
            q, user_id=user_id, capacity="resident", disease_id=disease_id,
            task_entity=PrimaryTask,
        )
        if exclude_enforced_project_encounter_sets:
            q = exclude_enforced_project_encounter_set_tasks(q, PrimaryTask)
            q = exclude_enforced_project_encounter_set_tasks(q, LinkedTask)
        rows = q.all()
        if rows:
            results[disease_name] = [
                {"id": row[0], "name": row[1], "count": row[2]}
                for row in rows
            ]

    return results
