"""
Utility functions for getting the next eligible dual grading tasks. 
"""

from sqlalchemy.orm import selectinload, aliased
from sqlalchemy import and_, exists, or_, func
from models import GradingTask, User, UserDiseaseUnitRole, LabUnit, Grade, TaskTracker, LinkedDiseaseGrading
from typing import Optional, Union, List
import random
from datetime import datetime, timedelta
from uuid import uuid4
from utils.env_loader import load_environment
from db_transaction_manager import transaction_scope
from utils.linkedGradingUtils import get_linked_disease_ids, get_primary_disease_id
from encounter_sets.grading_records import reconcile_active_packages
from tasks.lineage import valid_task_lineage

load_environment()

from utils.dualGradingEligibility import (
    _get_user_eligible_lab_unit_ids,
    _has_user_graded_task_4weeks,
    get_user_eligibility_for_task,
    has_user_graded_task,
)
from datetime import datetime, timedelta, timezone
from models import Grade


def _ensure_task_uuid(db, task: GradingTask) -> None:
    """Assign a uuid4 to the task if it was missing (legacy rows)."""
    if not getattr(task, "uuid", None):
        task.uuid = str(uuid4())
        db.add(task)
        db.flush()

    # Ensure the UUID is loaded in the current session to prevent DetachedInstanceError
    if task.uuid is None:
        # Refresh the task to ensure UUID is loaded
        db.refresh(task)


def _has_user_graded_task_6hr(db, user_id: int, task_id: int) -> bool:
    """
    Check if a user has graded a task in the last 6 hours (or configured timeframe).
    This is used for revision functionality to allow arbitrators to revise grades.
    
    Args:
        db: Database session
        user_id: The ID of the user
        task_id: The ID of the task
        
    Returns:
        True if user has graded the task in the last 6 hours, False otherwise
    """
    from datetime import datetime, timedelta, timezone
    import os
    
    # Get the revision timeframe from environment variable (default to 6 hours)
    revision_hours = int(os.getenv("ARBITRATOR_REVISION_HOURS", "6"))
    
    # Calculate the cutoff time
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=revision_hours)
    
    # Get all grades by this user for this task
    user_grades = db.query(Grade).filter(
        Grade.grader_user_id == user_id,
        Grade.task_id == task_id
    ).all()
    
    # Check if any of the grades were created recently
    for grade in user_grades:
        # Handle timezone-naive datetimes from the database
        grade_created_at = grade.created_at
        if grade_created_at.tzinfo is None:
            # Assume naive datetime is in UTC
            grade_created_at = grade_created_at.replace(tzinfo=timezone.utc)
        
        if grade_created_at >= cutoff_time:
            return True
    
    return False


def _exclude_linked_state_mismatches(db, query, disease_id: int):
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
        .where(valid_task_lineage(LinkedTask))
    )

    return query.filter(~mismatch_exists)


def _get_filtered_tasks(db, user_id: int, disease_id: int, role_slot: str, eligible_lab_unit_ids: list) -> list:
    """
    Get filtered tasks based on role slot and other criteria.
    
    Args:
        db: Database session
        user_id: The ID of the user
        disease_id: The disease ID
        role_slot: The role slot ('resident', 'resident2', or 'arbitrator')
        eligible_lab_unit_ids: List of lab unit IDs the user is eligible for
        
    Returns:
        List of filtered tasks
    """
    if role_slot == "arbitrator":
        reconcile_active_packages(db)

    # Build query for tasks
    query = db.query(GradingTask).filter(valid_task_lineage())
    
    # Filter by eligible lab units
    query = query.filter(GradingTask.lab_unit_id.in_(eligible_lab_unit_ids))
        
    # Filter by disease
    query = query.filter(GradingTask.disease_id == disease_id)
        
    # Filter by role-specific states and TaskTracker
    if role_slot == "arbitrator":
        linked_ids = get_linked_disease_ids(db, disease_id)
        if linked_ids:
             LinkedTask = aliased(GradingTask)
             
             # Tracker checks
             primary_tracker_exists = db.query(TaskTracker.id).filter(
                 TaskTracker.task_id == GradingTask.id,
                 TaskTracker.role_slot == role_slot
             ).exists()
             
             linked_tracker_exists = db.query(TaskTracker.id).filter(
                 TaskTracker.task_id == LinkedTask.id,
                 TaskTracker.role_slot == role_slot
             ).exists()

             query = query.outerjoin(
                 LinkedTask,
                 and_(
                     or_(
                         and_(GradingTask.encounter_file_id != None, GradingTask.encounter_file_id == LinkedTask.encounter_file_id),
                         and_(GradingTask.direct_image_upload_id != None, GradingTask.direct_image_upload_id == LinkedTask.direct_image_upload_id),
                         and_(GradingTask.patient_encounter_id != None, GradingTask.patient_encounter_id == LinkedTask.patient_encounter_id),
                         and_(GradingTask.encounter_set_image_id != None, GradingTask.encounter_set_image_id == LinkedTask.encounter_set_image_id),
                     ),
                     LinkedTask.disease_id.in_(linked_ids)
                 )
             ).filter(
                 or_(
                     and_(GradingTask.state == "arbitration", ~primary_tracker_exists),
                     and_(LinkedTask.state == "arbitration", ~linked_tracker_exists)
                 )
             )
        else:
             tracker_exists = db.query(TaskTracker.id).filter(
                 TaskTracker.task_id == GradingTask.id,
                 TaskTracker.role_slot == role_slot
             ).exists()
             query = query.filter(GradingTask.state == "arbitration", ~tracker_exists)
    elif role_slot == "resident":
        tracker_exists = db.query(TaskTracker.id).filter(
             TaskTracker.task_id == GradingTask.id,
             TaskTracker.role_slot == role_slot
        ).exists()
        query = query.filter(GradingTask.state == "pending", ~tracker_exists)
    elif role_slot == "resident2":
        tracker_exists = db.query(TaskTracker.id).filter(
             TaskTracker.task_id == GradingTask.id,
             TaskTracker.role_slot == role_slot
        ).exists()
        query = query.filter(GradingTask.state == "resident_done", ~tracker_exists)

    if role_slot in {"resident", "resident2"}:
        query = _exclude_linked_state_mismatches(db, query, disease_id)
    
    # Get all matching tasks
    tasks = query.all()
    
    # Filter out tasks that conflict with user's opposite resident slot on the same task
    filtered_tasks = []
    conflicting_slots: List[str] = []
    if role_slot == "resident":
        conflicting_slots = ["resident2"]
    elif role_slot == "resident2":
        conflicting_slots = ["resident"]

    for task in tasks:
        if not get_user_eligibility_for_task(db, user_id, task.id, role_slot):
            continue
        if conflicting_slots and has_user_graded_task(db, user_id, task.id, conflicting_slots):
            continue
        _ensure_task_uuid(db, task)
        filtered_tasks.append(task)
    
    return filtered_tasks


def _get_inconsistent_resident_tasks(db, user_id: int, disease_id: int, eligible_lab_unit_ids: list) -> list:
    """
    Surface tasks stuck in resident2_done with no resident grade so residents can complete them.

    These tasks exist because a Resident2 grade was ingested before the Resident grade.
    We keep them ahead of normal pending tasks to clear the inconsistency.
    """
    if not eligible_lab_unit_ids:
        return []

    resident2_exists = (
        db.query(Grade.id)
        .filter(and_(Grade.task_id == GradingTask.id, Grade.role_slot == "resident2"))
    )
    resident_missing = ~exists().where(and_(Grade.task_id == GradingTask.id, Grade.role_slot == "resident"))

    # Also check TaskTracker for inconsistent tasks
    tracker_exists = db.query(TaskTracker.id).filter(
         TaskTracker.task_id == GradingTask.id,
         TaskTracker.role_slot == "resident"
    ).exists()

    tasks = (
        db.query(GradingTask)
        .filter(GradingTask.lab_unit_id.in_(eligible_lab_unit_ids))
        .filter(GradingTask.disease_id == disease_id)
        .filter(valid_task_lineage())
        .filter(GradingTask.state == "resident2_done")
        .filter(resident_missing)
        .filter(resident2_exists.exists())
        .filter(~tracker_exists)
        .all()
    )

    filtered_tasks = []
    for task in tasks:
        if not get_user_eligibility_for_task(db, user_id, task.id, "resident"):
            continue
        if has_user_graded_task(db, user_id, task.id, ["resident2"]):
            continue
        _ensure_task_uuid(db, task)
        filtered_tasks.append(task)

    return filtered_tasks


def get_next_eligible_resident_task(user_id: int, disease_id: int, lab_unit_id: Optional[int] = None, db=None) -> Optional[Union[GradingTask, str]]:
    """
    Get the next eligible task for a resident user.
    
    Args:
        user_id: The ID of the user (must be a resident or admin)
        disease_id: The disease ID (required)
        lab_unit_id: Optional lab unit ID to filter by
        db: Optional database session (if not provided, a new session will be created)
        
    Returns:
        The next eligible GradingTask, None if no tasks are available,
        or a helpful message if no suitable tasks are found after 3 tries
    """
    # If db is provided, use it directly (dependency injection pattern)
    if db is not None:
        return _get_next_eligible_resident_task_with_session(user_id, disease_id, lab_unit_id, db)
    
    # Otherwise, use the context manager pattern
    with transaction_scope() as db:
        return _get_next_eligible_resident_task_with_session(user_id, disease_id, lab_unit_id, db)


def _get_next_eligible_resident_task_with_session(user_id: int, disease_id: int, lab_unit_id: Optional[int], db) -> Optional[Union[GradingTask, str]]:
    """
    Internal function that gets the next eligible resident task using an existing session.
    
    Args:
        user_id: The ID of the user (must be a resident or admin)
        disease_id: The disease ID (required)
        lab_unit_id: Optional lab unit ID to filter by
        db: Database session
        
    Returns:
        The next eligible GradingTask, None if no tasks are available,
        or a helpful message if no suitable tasks are found after 3 tries
    """
    # Get user's eligible lab unit IDs for resident role and specified disease
    eligible_lab_unit_ids = _get_user_eligible_lab_unit_ids(db, user_id, disease_id, "resident")
    if eligible_lab_unit_ids is None:
        return None
    
    # If a specific lab unit is requested, check if user is eligible for it
    if lab_unit_id:
        if lab_unit_id not in eligible_lab_unit_ids:
            return None
        # Filter to only the specified lab unit
        eligible_lab_unit_ids = [lab_unit_id]
    
    # Try up to 3 times to find a suitable task
    inconsistent_tasks = _get_inconsistent_resident_tasks(db, user_id, disease_id, eligible_lab_unit_ids)
    if inconsistent_tasks:
        return random.choice(inconsistent_tasks)

    for attempt in range(3):
        # Get filtered tasks
        tasks = _get_filtered_tasks(db, user_id, disease_id, "resident", eligible_lab_unit_ids)
        
        # If we have tasks, return a random one
        if tasks:
            return random.choice(tasks)
    
    # If we've tried 3 times and still don't have tasks, return a helpful message
    return "No suitable tasks available at this time. All tasks have been recently graded by you or no tasks match your criteria."


def get_next_eligible_resident2_task(user_id: int, disease_id: int, lab_unit_id: Optional[int] = None, db=None) -> Optional[Union[GradingTask, str]]:
    """
    Get the next eligible task for a resident2 user.
    
    Args:
        user_id: The ID of a resident-capacity user
        disease_id: The disease ID (required)
        lab_unit_id: Optional lab unit ID to filter by
        db: Optional database session (if not provided, a new session will be created)
        
    Returns:
        The next eligible GradingTask, None if no tasks are available,
        or a helpful message if no suitable tasks are found after 3 tries
    """
    # If db is provided, use it directly (dependency injection pattern)
    if db is not None:
        return _get_next_eligible_resident2_task_with_session(user_id, disease_id, lab_unit_id, db)
    
    # Otherwise, use the context manager pattern
    with transaction_scope() as db:
        return _get_next_eligible_resident2_task_with_session(user_id, disease_id, lab_unit_id, db)


def _get_next_eligible_resident2_task_with_session(user_id: int, disease_id: int, lab_unit_id: Optional[int], db) -> Optional[Union[GradingTask, str]]:
    """
    Internal function that gets the next eligible resident2 task using an existing session.
    
    Args:
        user_id: The ID of a resident-capacity user
        disease_id: The disease ID (required)
        lab_unit_id: Optional lab unit ID to filter by
        db: Database session
        
    Returns:
        The next eligible GradingTask, None if no tasks are available,
        or a helpful message if no suitable tasks are found after 3 tries
    """
    # Get user's eligible lab unit IDs for resident2 role and specified disease
    eligible_lab_unit_ids = _get_user_eligible_lab_unit_ids(db, user_id, disease_id, "resident2")
    if eligible_lab_unit_ids is None:
        return None
    
    # If a specific lab unit is requested, check if user is eligible for it
    if lab_unit_id:
        if lab_unit_id not in eligible_lab_unit_ids:
            return None
        # Filter to only the specified lab unit
        eligible_lab_unit_ids = [lab_unit_id]
    
    # Try up to 3 times to find a suitable task
    for attempt in range(3):
        # Get filtered tasks
        tasks = _get_filtered_tasks(db, user_id, disease_id, "resident2", eligible_lab_unit_ids)
        
        # If we have tasks, return a random one
        if tasks:
            return random.choice(tasks)
    
    # If we've tried 3 times and still don't have tasks, return a helpful message
    return "No suitable tasks available at this time. All tasks have been recently graded by you or no tasks match your criteria."


def get_next_eligible_arbitrator_task(user_id: int, disease_id: int, lab_unit_id: Optional[int] = None, db=None) -> Optional[Union[GradingTask, str]]:
    """
    Get the next eligible task for an arbitrator user.
    
    Args:
        user_id: The ID of the user (must be an ophthalmologist or admin)
        disease_id: The disease ID (required)
        lab_unit_id: Optional lab unit ID to filter by
        db: Optional database session (if not provided, a new session will be created)
        
    Returns:
        The next eligible GradingTask, None if no tasks are available,
        or a helpful message if no suitable tasks are found after 3 tries
    """
    # If db is provided, use it directly (dependency injection pattern)
    if db is not None:
        return _get_next_eligible_arbitrator_task_with_session(user_id, disease_id, lab_unit_id, db)
    
    # Otherwise, use the context manager pattern
    with transaction_scope() as db:
        return _get_next_eligible_arbitrator_task_with_session(user_id, disease_id, lab_unit_id, db)


def _get_next_eligible_arbitrator_task_with_session(user_id: int, disease_id: int, lab_unit_id: Optional[int], db) -> Optional[Union[GradingTask, str]]:
    """
    Internal function that gets the next eligible arbitrator task using an existing session.
    
    Args:
        user_id: The ID of the user (must be an ophthalmologist or admin)
        disease_id: The disease ID (required)
        lab_unit_id: Optional lab unit ID to filter by
        db: Database session
        
    Returns:
        The next eligible GradingTask, None if no tasks are available,
        or a helpful message if no suitable tasks are found after 3 tries
    """
    # Get user's eligible lab unit IDs for arbitrator role and specified disease
    eligible_lab_unit_ids = _get_user_eligible_lab_unit_ids(db, user_id, disease_id, "arbitrator")
    if eligible_lab_unit_ids is None:
        return None
    
    # If a specific lab unit is requested, check if user is eligible for it
    if lab_unit_id:
        if lab_unit_id not in eligible_lab_unit_ids:
            return None
        # Filter to only the specified lab unit
        eligible_lab_unit_ids = [lab_unit_id]
    
    # Try up to 3 times to find a suitable task
    for attempt in range(3):
        # Get filtered tasks
        tasks = _get_filtered_tasks(db, user_id, disease_id, "arbitrator", eligible_lab_unit_ids)
        
        # If we have tasks, return a random one
        if tasks:
            return random.choice(tasks)
    
    # If we've tried 3 times and still don't have tasks, return a helpful message
    return "No suitable tasks available at this time. All tasks have been recently graded by you or no tasks match your criteria."


def _atomically_get_and_lock_task(db, user_id: int, disease_id: int, role_slot: str, eligible_lab_unit_ids: list):
    """
    Atomically get and lock a task for a user to prevent race conditions.
    This function uses SELECT FOR UPDATE to ensure no other user can get the same task.
    
    Args:
        db: Database session
        user_id: The ID of the user
        disease_id: The disease ID
        role_slot: The role slot ('resident', 'resident2', or 'arbitrator')
        eligible_lab_unit_ids: List of lab unit IDs the user is eligible for
    
    Returns:
        The locked GradingTask or None if no eligible tasks are available
    """
    if role_slot == "arbitrator":
        reconcile_active_packages(db)

    # Build the base query
    query = db.query(GradingTask).filter(
        GradingTask.lab_unit_id.in_(eligible_lab_unit_ids),
        GradingTask.disease_id == disease_id,
        valid_task_lineage(),
    )
    
    # Filter by role-specific states and TaskTracker
    if role_slot == "arbitrator":
        linked_ids = get_linked_disease_ids(db, disease_id)
        if linked_ids:
             LinkedTask = aliased(GradingTask)
             
             # Tracker checks
             primary_tracker_exists = db.query(TaskTracker.id).filter(
                 TaskTracker.task_id == GradingTask.id,
                 TaskTracker.role_slot == role_slot
             ).exists()
             
             linked_tracker_exists = db.query(TaskTracker.id).filter(
                 TaskTracker.task_id == LinkedTask.id,
                 TaskTracker.role_slot == role_slot
             ).exists()

             query = query.outerjoin(
                 LinkedTask,
                 and_(
                 or_(
                         and_(GradingTask.encounter_file_id != None, GradingTask.encounter_file_id == LinkedTask.encounter_file_id),
                         and_(GradingTask.direct_image_upload_id != None, GradingTask.direct_image_upload_id == LinkedTask.direct_image_upload_id),
                         and_(GradingTask.patient_encounter_id != None, GradingTask.patient_encounter_id == LinkedTask.patient_encounter_id),
                         and_(GradingTask.encounter_set_image_id != None, GradingTask.encounter_set_image_id == LinkedTask.encounter_set_image_id),
                     ),
                     LinkedTask.disease_id.in_(linked_ids)
                 )
             ).filter(
                 or_(
                     and_(GradingTask.state == "arbitration", ~primary_tracker_exists),
                     and_(LinkedTask.state == "arbitration", ~linked_tracker_exists)
                 )
             )
        else:
            tracker_exists = db.query(TaskTracker.id).filter(
                 TaskTracker.task_id == GradingTask.id,
                 TaskTracker.role_slot == role_slot
            ).exists()
            query = query.filter(GradingTask.state == "arbitration", ~tracker_exists)
    elif role_slot == "resident":
        tracker_exists = db.query(TaskTracker.id).filter(
             TaskTracker.task_id == GradingTask.id,
             TaskTracker.role_slot == role_slot
        ).exists()
        query = query.filter(GradingTask.state == "pending", ~tracker_exists)
    elif role_slot == "resident2":
        tracker_exists = db.query(TaskTracker.id).filter(
             TaskTracker.task_id == GradingTask.id,
             TaskTracker.role_slot == role_slot
        ).exists()
        query = query.filter(GradingTask.state == "resident_done", ~tracker_exists)

    if role_slot in {"resident", "resident2"}:
        query = _exclude_linked_state_mismatches(db, query, disease_id)
    
    conflicting_slots: List[str] = []
    if role_slot == "resident":
        conflicting_slots = ["resident2"]
    elif role_slot == "resident2":
        conflicting_slots = ["resident"]

    if conflicting_slots:
        conflict_exists = (
            db.query(Grade.id)
            .filter(
                Grade.task_id == GradingTask.id,
                Grade.grader_user_id == user_id,
                Grade.role_slot.in_(conflicting_slots),
            )
        )
        query = query.filter(~conflict_exists.exists())

    # Resolve project allocation before locking. Re-run the original filtered
    # query for the selected row under FOR UPDATE so its state is revalidated.
    candidates = query.order_by(func.random()).yield_per(100)
    for candidate in candidates:
        if not get_user_eligibility_for_task(db, user_id, candidate.id, role_slot):
            continue
        if role_slot == "arbitrator" and _has_user_graded_task_4weeks(db, user_id, candidate.id):
            continue
        task = query.filter(GradingTask.id == candidate.id).with_for_update().first()
        if task is not None:
            _ensure_task_uuid(db, task)
            return task

    return None


def get_next_linked_followup_task_atomic(
    user_id: int,
    primary_disease_id: int,
    linked_disease_id: int,
    db=None,
):
    """
    Get the next eligible linked-followup task for a user, preferring resident2 when available.
    Returns (task, slot) or (None, None).
    """
    if db is not None:
        return _get_next_linked_followup_task_atomic_with_session(
            user_id, primary_disease_id, linked_disease_id, db
        )

    with transaction_scope() as db:
        return _get_next_linked_followup_task_atomic_with_session(
            user_id, primary_disease_id, linked_disease_id, db
        )


def _get_next_linked_followup_task_atomic_with_session(
    user_id: int,
    primary_disease_id: int,
    linked_disease_id: int,
    db,
):
    user = db.query(User).options(selectinload(User.roles)).filter(User.id == user_id).first()
    if not user:
        return None, None

    slot_order = ["resident2", "resident"]

    for slot in slot_order:
        eligible_lab_unit_ids = _get_user_eligible_lab_unit_ids(db, user_id, primary_disease_id, slot)
        if not eligible_lab_unit_ids:
            continue

        task = _atomically_get_and_lock_linked_followup_task(
            db,
            user_id,
            primary_disease_id,
            linked_disease_id,
            slot,
            eligible_lab_unit_ids,
        )
        if task is not None:
            return task, slot

    return None, None


def _atomically_get_and_lock_linked_followup_task(
    db,
    user_id: int,
    primary_disease_id: int,
    linked_disease_id: int,
    slot: str,
    eligible_lab_unit_ids: list,
):
    PrimaryTask = aliased(GradingTask)
    LinkedTask = aliased(GradingTask)

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
        and_(
            PrimaryTask.encounter_set_image_id.isnot(None),
            PrimaryTask.encounter_set_image_id == LinkedTask.encounter_set_image_id,
        ),
    )

    if slot == "resident2":
        mismatch_filter = and_(
            PrimaryTask.state.in_(["resident2_done", "final"]),
            LinkedTask.state == "resident_done",
        )
    else:
        mismatch_filter = and_(
            PrimaryTask.state == "resident_done",
            LinkedTask.state == "pending",
        )

    linked_tracker_exists = db.query(TaskTracker.id).filter(
        TaskTracker.task_id == LinkedTask.id,
        TaskTracker.role_slot == slot,
    ).exists()

    conflicting_slots = ["resident2"] if slot == "resident" else ["resident"]
    conflict_exists = (
        db.query(Grade.id)
        .filter(
            Grade.task_id == LinkedTask.id,
            Grade.grader_user_id == user_id,
            Grade.role_slot.in_(conflicting_slots),
        )
    )

    query = (
        db.query(LinkedTask)
        .join(PrimaryTask, image_match)
        .join(
            LinkedDiseaseGrading,
            and_(
                LinkedDiseaseGrading.primary_disease_id == PrimaryTask.disease_id,
                LinkedDiseaseGrading.linked_disease_id == LinkedTask.disease_id,
                LinkedDiseaseGrading.is_active.is_(True),
            ),
        )
        .filter(PrimaryTask.disease_id == primary_disease_id)
        .filter(LinkedTask.disease_id == linked_disease_id)
        .filter(PrimaryTask.lab_unit_id.in_(eligible_lab_unit_ids))
        .filter(valid_task_lineage(PrimaryTask))
        .filter(valid_task_lineage(LinkedTask))
        .filter(mismatch_filter)
        .filter(~linked_tracker_exists)
        .filter(~conflict_exists.exists())
    )

    for candidate in query.order_by(func.random()).yield_per(100):
        if not get_user_eligibility_for_task(db, user_id, candidate.id, slot):
            continue
        task = query.filter(LinkedTask.id == candidate.id).with_for_update().first()
        if task is not None:
            _ensure_task_uuid(db, task)
            return task
    return None


def _lock_inconsistent_resident_task(db, user_id: int, disease_id: int, eligible_lab_unit_ids: list):
    """Lock a resident task stuck in resident2_done with no resident grade."""
    if not eligible_lab_unit_ids:
        return None

    resident2_exists = (
        db.query(Grade.id)
        .filter(and_(Grade.task_id == GradingTask.id, Grade.role_slot == "resident2"))
    )
    resident_missing = ~exists().where(and_(Grade.task_id == GradingTask.id, Grade.role_slot == "resident"))

    conflict_exists = (
        db.query(Grade.id)
        .filter(
            Grade.task_id == GradingTask.id,
            Grade.grader_user_id == user_id,
            Grade.role_slot.in_(["resident2"]),
        )
    )

    # Tracker check
    tracker_exists = db.query(TaskTracker.id).filter(
         TaskTracker.task_id == GradingTask.id,
         TaskTracker.role_slot == "resident"
    ).exists()

    query = (
        db.query(GradingTask)
        .filter(GradingTask.lab_unit_id.in_(eligible_lab_unit_ids))
        .filter(GradingTask.disease_id == disease_id)
        .filter(GradingTask.state == "resident2_done")
        .filter(valid_task_lineage())
        .filter(resident_missing)
        .filter(resident2_exists.exists())
        .filter(~conflict_exists.exists())
        .filter(~tracker_exists)
    )
    for candidate in query.order_by(func.random()).yield_per(100):
        if not get_user_eligibility_for_task(db, user_id, candidate.id, "resident"):
            continue
        task = query.filter(GradingTask.id == candidate.id).with_for_update().first()
        if task is not None:
            _ensure_task_uuid(db, task)
            return task

    return None


def get_next_eligible_resident_task_atomic(user_id: int, disease_id: int, lab_unit_id: Optional[int] = None, db=None) -> Optional[Union[GradingTask, str]]:
    """
    Get the next eligible task for a resident user with atomic locking to prevent race conditions.
    
    Args:
        user_id: The ID of the user (must be a resident or admin)
        disease_id: The disease ID (required)
        lab_unit_id: Optional lab unit ID to filter by
        db: Optional database session (if not provided, a new session will be created)
        
    Returns:
        The next eligible GradingTask, None if no tasks are available,
        or a helpful message if no suitable tasks are found after 3 tries
    """
    # If db is provided, use it directly (dependency injection pattern)
    if db is not None:
        return _get_next_eligible_resident_task_atomic_with_session(user_id, disease_id, lab_unit_id, db)
    
    # Otherwise, use the context manager pattern
    with transaction_scope() as db:
        return _get_next_eligible_resident_task_atomic_with_session(user_id, disease_id, lab_unit_id, db)


def _get_next_eligible_resident_task_atomic_with_session(user_id: int, disease_id: int, lab_unit_id: Optional[int], db) -> Optional[Union[GradingTask, str]]:
    """
    Internal function that gets the next eligible resident task with atomic locking using an existing session.
    
    Args:
        user_id: The ID of the user (must be a resident or admin)
        disease_id: The disease ID (required)
        lab_unit_id: Optional lab unit ID to filter by
        db: Database session
        
    Returns:
        The next eligible GradingTask, None if no tasks are available,
        or a helpful message if no suitable tasks are found after 3 tries
    """
    # Get user's eligible lab unit IDs for resident role and specified disease
    eligible_lab_unit_ids = _get_user_eligible_lab_unit_ids(db, user_id, disease_id, "resident")
    if eligible_lab_unit_ids is None:
        return None
    
    # If a specific lab unit is requested, check if user is eligible for it
    if lab_unit_id:
        if lab_unit_id not in eligible_lab_unit_ids:
            return None
        # Filter to only the specified lab unit
        eligible_lab_unit_ids = [lab_unit_id]
    
    # Try up to 3 times to find a suitable task with atomic locking
    for attempt in range(3):
        inconsistent_task = _lock_inconsistent_resident_task(db, user_id, disease_id, eligible_lab_unit_ids)
        if inconsistent_task:
            return inconsistent_task

    for attempt in range(3):
        task = _atomically_get_and_lock_task(db, user_id, disease_id, "resident", eligible_lab_unit_ids)
        if task:
            return task
    
    # If we've tried 3 times and still don't have tasks, return a helpful message
    return "No suitable tasks available at this time. All tasks have been recently graded by you or no tasks match your criteria."


def get_next_eligible_resident2_task_atomic(user_id: int, disease_id: int, lab_unit_id: Optional[int] = None, db=None) -> Optional[Union[GradingTask, str]]:
    """
    Get the next eligible task for a resident2 user with atomic locking to prevent race conditions.
    
    Args:
        user_id: The ID of a resident-capacity user
        disease_id: The disease ID (required)
        lab_unit_id: Optional lab unit ID to filter by
        db: Optional database session (if not provided, a new session will be created)
        
    Returns:
        The next eligible GradingTask, None if no tasks are available,
        or a helpful message if no suitable tasks are found after 3 tries
    """
    # If db is provided, use it directly (dependency injection pattern)
    if db is not None:
        return _get_next_eligible_resident2_task_atomic_with_session(user_id, disease_id, lab_unit_id, db)
    
    # Otherwise, use the context manager pattern
    with transaction_scope() as db:
        return _get_next_eligible_resident2_task_atomic_with_session(user_id, disease_id, lab_unit_id, db)


def _get_next_eligible_resident2_task_atomic_with_session(user_id: int, disease_id: int, lab_unit_id: Optional[int], db) -> Optional[Union[GradingTask, str]]:
    """
    Internal function that gets the next eligible resident2 task with atomic locking using an existing session.
    
    Args:
        user_id: The ID of a resident-capacity user
        disease_id: The disease ID (required)
        lab_unit_id: Optional lab unit ID to filter by
        db: Database session
        
    Returns:
        The next eligible GradingTask, None if no tasks are available,
        or a helpful message if no suitable tasks are found after 3 tries
    """
    # Get user's eligible lab unit IDs for resident2 role and specified disease
    eligible_lab_unit_ids = _get_user_eligible_lab_unit_ids(db, user_id, disease_id, "resident2")
    if eligible_lab_unit_ids is None:
        return None
    
    # If a specific lab unit is requested, check if user is eligible for it
    if lab_unit_id:
        if lab_unit_id not in eligible_lab_unit_ids:
            return None
        # Filter to only the specified lab unit
        eligible_lab_unit_ids = [lab_unit_id]
    
    # Try up to 3 times to find a suitable task with atomic locking
    for attempt in range(3):
        task = _atomically_get_and_lock_task(db, user_id, disease_id, "resident2", eligible_lab_unit_ids)
        if task:
            return task
    
    # If we've tried 3 times and still don't have tasks, return a helpful message
    return "No suitable tasks available at this time. All tasks have been recently graded by you or no tasks match your criteria."


def get_next_eligible_arbitrator_task_atomic(user_id: int, disease_id: int, lab_unit_id: Optional[int] = None, db=None) -> Optional[Union[GradingTask, str]]:
    """
    Get the next eligible task for an arbitrator user with atomic locking to prevent race conditions.
    
    Args:
        user_id: The ID of the user (must be an ophthalmologist or admin)
        disease_id: The disease ID (required)
        lab_unit_id: Optional lab unit ID to filter by
        db: Optional database session (if not provided, a new session will be created)
        
    Returns:
        The next eligible GradingTask, None if no tasks are available,
        or a helpful message if no suitable tasks are found after 3 tries
    """
    # If db is provided, use it directly (dependency injection pattern)
    if db is not None:
        return _get_next_eligible_arbitrator_task_atomic_with_session(user_id, disease_id, lab_unit_id, db)
    
    # Otherwise, use the context manager pattern
    with transaction_scope() as db:
        return _get_next_eligible_arbitrator_task_atomic_with_session(user_id, disease_id, lab_unit_id, db)


def _get_next_eligible_arbitrator_task_atomic_with_session(user_id: int, disease_id: int, lab_unit_id: Optional[int], db) -> Optional[Union[GradingTask, str]]:
    """
    Internal function that gets the next eligible arbitrator task with atomic locking using an existing session.
    
    Args:
        user_id: The ID of the user (must be an ophthalmologist or admin)
        disease_id: The disease ID (required)
        lab_unit_id: Optional lab unit ID to filter by
        db: Database session
        
    Returns:
        The next eligible GradingTask, None if no tasks are available,
        or a helpful message if no suitable tasks are found after 3 tries
    """
    # Get user's eligible lab unit IDs for arbitrator role and specified disease
    eligible_lab_unit_ids = _get_user_eligible_lab_unit_ids(db, user_id, disease_id, "arbitrator")
    if eligible_lab_unit_ids is None:
        return None
    
    # If a specific lab unit is requested, check if user is eligible for it
    if lab_unit_id:
        if lab_unit_id not in eligible_lab_unit_ids:
            return None
        # Filter to only the specified lab unit
        eligible_lab_unit_ids = [lab_unit_id]
    
    # Try up to 3 times to find a suitable task with atomic locking
    for attempt in range(3):
        task = _atomically_get_and_lock_task(db, user_id, disease_id, "arbitrator", eligible_lab_unit_ids)
        if task:
            return task
    
    # If we've tried 3 times and still don't have tasks, return a helpful message
    return "No suitable tasks available at this time. All tasks have been recently graded by you or no tasks match your criteria."
