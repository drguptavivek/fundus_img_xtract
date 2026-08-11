"""
Hospital-level scoping utilities for query filtering.

This module provides utilities to apply hospital and lab-unit scoping to queries,
supporting both hospital-bound operations and cross-hospital grading.
"""
from typing import Any, Set
from sqlalchemy.orm import Query
from models import User, LabUnit, Hospital
from db_transaction_manager import get_db_session
from flask import request


# Cross-hospital operations (no hospital filter applied)
CROSS_HOSPITAL_OPERATIONS = {
    'grading',
    'arbitration', 
    'research',
    'training',
}


def is_cross_hospital_operation(operation: str) -> bool:
    """
    Check if an operation is cross-hospital.
    
    Args:
        operation: Operation name (e.g., 'grading', 'upload', 'analytics')
        
    Returns:
        True if operation is cross-hospital, False if hospital-bound
    """
    return operation in CROSS_HOSPITAL_OPERATIONS


def get_user_lab_units_in_hospital(
    user_id: int, 
    hospital_id: int | None = None,
    db=None
) -> Set[int]:
    """
    Get lab unit IDs for a user, optionally filtered by hospital.
    
    Args:
        user_id: User ID
        hospital_id: Optional hospital ID to filter by. If None, uses user's hospital.
        db: Optional database session (for testing)
        
    Returns:
        Set of lab unit IDs the user can access in the specified hospital
    """
    close_session = False
    if db is None:
        from db_transaction_manager import get_db_session
        db = get_db_session().__enter__()
        close_session = True
    
    try:
        user = db.query(User).filter_by(id=user_id).first()
        if not user:
            return set()

        # Admins see all assigned lab units across hospitals.
        if user.has_role("admin"):
            return {lu.id for lu in user.lab_units}

        # Local admins and regular users are filtered by hospital.
        target_hospital_id = hospital_id or user.hospital_id
        if not target_hospital_id:
            return set()
        
        # Return only lab units from target hospital
        return {
            lu.id for lu in user.lab_units
            if lu.hospital_id == target_hospital_id
        }
    finally:
        if close_session:
            db.close()


def validate_lab_unit_hospital_match(
    user_id: int, 
    lab_unit_id: int,
    db=None
) -> bool:
    """
    Validate that a lab unit belongs to the user's hospital.
    
    Args:
        user_id: User ID
        lab_unit_id: Lab unit ID to validate
        db: Optional database session (for testing)
        
        Returns:
        True if lab unit belongs to user's hospital
    
    Raises:
        ValueError: If user not found or has no hospital
    """
    close_session = False
    if db is None:
        from db_transaction_manager import get_db_session
        db = get_db_session().__enter__()
        close_session = True
    
    try:
        user = db.query(User).filter_by(id=user_id).first()
        if not user:
            raise ValueError(f"User {user_id} not found")

        if user.has_role("admin"):
            return True
        
        if not user.hospital_id:
            raise ValueError(f"User {user_id} has no hospital assignment")
        
        # Check if lab unit belongs to user's hospital
        lab_unit = db.query(LabUnit).filter_by(id=lab_unit_id).first()
        if not lab_unit:
            return False
        
        return lab_unit.hospital_id == user.hospital_id
    finally:
        if close_session:
            db.close()


def apply_scoping(query: Query, model_class: Any, user: User, operation: str) -> Query:
    """
    Apply appropriate scoping (hospital & lab unit) based on operation type.
    
    This is the main entry point for query filtering. It applies:
    1. Hospital-level filtering (for hospital-bound operations)
    2. Lab-unit-level filtering (for User-LabUnit scoped operations)
    3. No filtering for cross-hospital operations (grading, dataset creation, etc.)
    
    Args:
        query: SQLAlchemy query to filter
        model_class: Model class being queried (must have hospital_id and/or lab_unit_id)
        user: Current user
        operation: Operation type ('grading', 'upload', 'analytics', etc.)
        
    Returns:
        Filtered query
        
    Examples:
        # Hospital-bound upload operation
        images = db.query(DirectImageUpload)
        images = apply_scoping(images, DirectImageUpload, current_user, 'upload')
        
        # Cross-hospital grading operation (no hospital filter)
        tasks = db.query(GradingTask)
        tasks = apply_scoping(tasks, GradingTask, current_user, 'grading')
    """
    # Admins can see all hospitals and lab units.
    if user.has_role('admin'):
        return query

    # Dataset Creator: cross-hospital access for creation, research, training
    if user.has_role('dataset_creator') and operation in {'dataset_creation', 'research', 'training'}:
        return query

    # Cross-hospital operations (NO hospital filter)
    if is_cross_hospital_operation(operation):
        if (
            operation in {"dataset_creation", "research", "training"}
            and hasattr(model_class, "project_id")
            and hasattr(model_class, "lab_unit_id")
        ):
            from encounter_sets.permissions import (
                CAPABILITY_DATASET_CREATION,
                apply_project_permission_scope,
            )
            return apply_project_permission_scope(
                query, model_class, user, CAPABILITY_DATASET_CREATION
            )
        # Grading uses Slot-LabUnit scoping (via UserDiseaseUnitRole)
        # No additional filtering needed here
        return query
    
    # Helper to support both legacy Query (.filter) and modern Select (.where)
    def apply_filter(q, *args):
        if hasattr(q, 'filter'):
            return q.filter(*args)
        return q.where(*args)

    # Hospital-bound operations (APPLY hospital filter)
    if not user.hospital_id:
        # No hospital assignment = no access
        return apply_filter(query, model_class.id == None)  # Empty result

    # Apply hospital filter for non-admin users (if model has hospital_id)
    if hasattr(model_class, 'hospital_id'):
        query = apply_filter(query, model_class.hospital_id == user.hospital_id)
    elif model_class == Hospital:
        query = apply_filter(query, Hospital.id == user.hospital_id)
    
    # Apply lab unit filter (if model has lab_unit_id)
    if hasattr(model_class, 'lab_unit_id'):
        # If model doesn't have hospital_id but has lab_unit_id, we MUST filter by hospital via LabUnit join
        if not hasattr(model_class, 'hospital_id'):
             # We need to join with LabUnit to filter by hospital
             query = query.join(LabUnit, model_class.lab_unit_id == LabUnit.id)
             query = apply_filter(query, LabUnit.hospital_id == user.hospital_id)
        
        # Site admins see ALL lab units in their hospital (no further restriction)
        # Regular users are restricted to their assigned lab units
        if not user.has_role('local_admin'):
            # Regular user - restrict to assigned lab units
            if user.lab_units:
                # Only include lab units from user's hospital
                user_lab_unit_ids = [
                    lu.id for lu in user.lab_units
                    if lu.hospital_id == user.hospital_id
                ]
                
                if user_lab_unit_ids:
                    query = apply_filter(query, model_class.lab_unit_id.in_(user_lab_unit_ids))
                else:
                    # No lab units in user's hospital - no access
                    return apply_filter(query, model_class.id == None)
            else:
                # Regular user with no lab units - no access
                return apply_filter(query, model_class.id == None)
    
    if (
        operation in {"analytics", "dataset_creation"}
        and hasattr(model_class, "project_id")
        and hasattr(model_class, "lab_unit_id")
    ):
        from encounter_sets.permissions import (
            CAPABILITY_ANALYTICS_VIEW,
            CAPABILITY_DATASET_CREATION,
            apply_project_permission_scope,
        )
        query = apply_project_permission_scope(
            query,
            model_class,
            user,
            (
                CAPABILITY_ANALYTICS_VIEW
                if operation == "analytics"
                else CAPABILITY_DATASET_CREATION
            ),
        )

    return query



def determine_scoping_context() -> str:
    """
    Determine the scoping context based on the request (referrer/params).
    
    Returns:
        'grading' if context implies grading application (allows cross-hospital),
        'upload' otherwise (strict isolation).
    """
    try:
        # Check if we are in a request context
        if not request:
            return 'upload'
            
        # 1. Check explicit query parameter
        if request.args.get('context') == 'grading':
            return 'grading'
            
        # 2. Check Referrer
        referrer = request.referrer
        if referrer:
            # If user is coming from grading pages
            if '/grade/' in referrer or '/grading/' in referrer:
                return 'grading'
    except RuntimeError:
        # Not in a request context
        return 'upload'
            
    # Default to strict isolation
    return 'upload'


__all__ = [
    'CROSS_HOSPITAL_OPERATIONS',
    'is_cross_hospital_operation',
    'get_user_lab_units_in_hospital',
    'validate_lab_unit_hospital_match',
    'apply_scoping',
    'determine_scoping_context',
]
