"""
Hospital scoping API endpoints.

Provides frontend with hospital context and operation scope information.
"""
from flask import jsonify
from flask_login import current_user, login_required
from auth.roles import roles_required
from . import api_bp


@api_bp.route("/user/hospital-context", methods=["GET"])
@login_required
def get_user_hospital_context():
    """
    Get hospital scoping context for current user.
    
    Used by frontend to determine UI behavior (show/hide hospital filters, etc.)
    
    Returns:
        {
            'user_id': int,
            'is_master_admin': bool,
            'hospital_id': int | None,
            'hospital_name': str | None,
            'can_access_multiple_hospitals': bool
        }
    """
    hospital_name = None
    if current_user.hospital:
        hospital_name = current_user.hospital.name
    
    return jsonify({
        'user_id': current_user.id,
        'is_master_admin': current_user.is_master_admin,
        'hospital_id': current_user.hospital_id,
        'hospital_name': hospital_name,
        'can_access_multiple_hospitals': current_user.has_role('admin', 'local_admin'),
    })


@api_bp.route("/scoping/operation/<operation_name>", methods=["GET"])
@login_required
def check_operation_scope(operation_name):
    """
    Check if an operation is cross-hospital or hospital-bound.
    
    Used by frontend to determine whether to show hospital filters.
    
    Args:
        operation_name: Name of operation (grading, upload, analytics, etc.)
    
    Returns:
        {
            'operation': str,
            'is_cross_hospital': bool,
            'user_is_master_admin': bool,
            'show_hospital_filter': bool
        }
    """
    from utils.hospital_scoping import is_cross_hospital_operation
    
    is_cross = is_cross_hospital_operation(operation_name)
    
    # Hospital filter should only show for master admin
    # OR for cross-hospital operations where user needs to filter
    show_filter = current_user.has_role('admin', 'local_admin')
    
    return jsonify({
        'operation': operation_name,
        'is_cross_hospital': is_cross,
        'user_is_master_admin': current_user.is_master_admin,
        'show_hospital_filter': show_filter,
    })
