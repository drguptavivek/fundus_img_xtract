"""
Hospital-level scoping utilities for query filtering.

This module provides utilities to apply hospital and lab-unit scoping to queries,
supporting both hospital-bound operations and cross-hospital grading.
"""
from typing import Any, Set
from sqlalchemy.orm import Query
from models import User, LabUnit
from db_transaction_manager import get_db_session
from flask import request


# Cross-hospital operations (no hospital filter applied)
CROSS_HOSPITAL_OPERATIONS = {
    'grading',
    'arbitration', 
    'dataset_creation',
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
        
        # Master admin sees all
        if user.is_master_admin:
            if hospital_id:
                # Get all lab units in specified hospital
                lab_units = db.query(LabUnit.id).filter_by(hospital_id=hospital_id).all()
                return {lu[0] for lu in lab_units}
            else:
                # Get all lab units
                lab_units = db.query(LabUnit.id).all()
                return {lu[0] for lu in lab_units}
        
        # Regular user - filter by hospital
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
        True if lab unit belongs to user's hospital (or user is master admin)
    
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
        
        # Master admin can access any lab unit
        if user.is_master_admin:
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
    # Master admin bypasses all filtering
    if user.is_master_admin:
        return query
    
        return query
    
    # Dataset Creator: cross-hospital access for creation, research, training
    if user.has_role('dataset_creator') and operation in {'dataset_creation', 'research', 'training'}:
        return query

    # Cross-hospital operations (NO hospital filter)
    if is_cross_hospital_operation(operation):
        # Grading uses Slot-LabUnit scoping (via UserDiseaseUnitRole)
        # No additional filtering needed here
        return query
    
    # Hospital-bound operations (APPLY hospital filter)
    if not user.hospital_id:
        # No hospital assignment = no access
        return query.filter(model_class.id == None)  # Empty result
    
    # Apply hospital filter (if model has hospital_id)
    if hasattr(model_class, 'hospital_id'):
        query = query.filter(model_class.hospital_id == user.hospital_id)
    
    # Apply lab unit filter (if model has lab_unit_id and user has assignments)
    if hasattr(model_class, 'lab_unit_id') and user.lab_units:
        # Only include lab units from user's hospital
        user_lab_unit_ids = [
            lu.id for lu in user.lab_units
            if lu.hospital_id == user.hospital_id
        ]
        
        if user_lab_unit_ids:
            query = query.filter(model_class.lab_unit_id.in_(user_lab_unit_ids))
        else:
            # No lab units in user's hospital
            return query.filter(model_class.id == None)
    
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
