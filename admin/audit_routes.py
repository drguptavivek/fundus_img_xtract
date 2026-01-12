"""Admin routes for sensitive operations audit."""

from flask import render_template, request, jsonify
import logging
from sqlalchemy import select, desc
from sqlalchemy.orm import joinedload

from auth.roles import roles_required
from models import SensitiveOperationAudit, User
from db_transaction_manager import get_db_session
from utils.log_sanitize import sanitize_log_value

logger = logging.getLogger('admin.audit')

@roles_required("admin")
def sensitive_operations_audit():
    """View sensitive operations audit log."""
    page = request.args.get('page', 1, type=int)
    per_page = 50
    
    # Filter parameters
    operation_type = request.args.get('operation_type')
    status = request.args.get('status')
    username = request.args.get('username')
    
    with get_db_session() as db:
        query = select(SensitiveOperationAudit).options(joinedload(SensitiveOperationAudit.user))
        
        # Apply filters
        if operation_type:
            query = query.where(SensitiveOperationAudit.operation_type == operation_type)
        
        if status:
            query = query.where(SensitiveOperationAudit.status == status)
            
        if username:
            query = query.join(User).where(User.username.ilike(f"%{username}%"))
            
        # Get total count for pagination
        # Note: simplistic count for now, optimization might be needed for large datasets
        # total_query = select(func.count()).select_from(query.subquery())
        # total = db.execute(total_query).scalar()
        
        # Order by newest first
        query = query.order_by(desc(SensitiveOperationAudit.created_at))
        
        # Pagination
        query = query.limit(per_page).offset((page - 1) * per_page)
        
        results = db.execute(query).scalars().all()
        
        # Get unique operation types for filter dropdown
        op_types_query = select(SensitiveOperationAudit.operation_type).distinct().order_by(SensitiveOperationAudit.operation_type)
        operation_types = db.execute(op_types_query).scalars().all()
        
    return render_template(
        "admin/sensitive_operations.html",
        audit_logs=results,
        page=page,
        operation_types=operation_types,
        current_filters={
            'operation_type': operation_type,
            'status': status,
            'username': username
        }
    )

@roles_required("admin")
def sensitive_operation_details(log_id):
    """Get details for a specific audit log entry via AJAX."""
    with get_db_session() as db:
        log_entry = db.get(SensitiveOperationAudit, log_id)
        
        if not log_entry:
            return jsonify({'error': 'Log entry not found'}), 404
            
        return jsonify({
            'id': log_entry.id,
            'operation_type': log_entry.operation_type,
            'status': log_entry.status,
            'user': log_entry.user.username if log_entry.user else 'System/Deleted',
            'ip_address': log_entry.ip_address,
            'created_at': log_entry.created_at.isoformat(),
            'request_details': log_entry.get_request_details(),
            'result_details': log_entry.get_result_details()
        })
