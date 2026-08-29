"""Admin routes for sensitive operations audit."""

from flask import render_template, request, jsonify, session
import logging
from sqlalchemy import select, desc
from sqlalchemy.orm import joinedload

from auth.roles import roles_required
from models import SensitiveOperationAudit, User
from db_transaction_manager import get_db_session
from utils.log_sanitize import sanitize_log_value, escape_like

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
    
    from flask_login import current_user
    
    with get_db_session() as db:
        # Re-fetch current_user to ensure it's attached to the current session
        # This prevents DetachedInstanceError in templates
        attached_user = None
        user_id = session.get('_user_id')
        
        if user_id:
            from models import LabUnit
            attached_user = db.execute(
                select(User).options(
                    joinedload(User.roles),
                    joinedload(User.lab_units).joinedload(LabUnit.hospital),
                    joinedload(User.hospital)
                ).where(User.id == int(user_id))
            ).unique().scalar_one_or_none()

        query = select(SensitiveOperationAudit).options(joinedload(SensitiveOperationAudit.user))
        
        # Apply filters
        if operation_type:
            query = query.where(SensitiveOperationAudit.operation_type == operation_type)
        
        if status:
            query = query.where(SensitiveOperationAudit.status == status)
            
        if username:
            query = query.join(User).where(User.username.ilike(f"%{escape_like(username)}%", escape="\\"))
            
        # Get total count for pagination
        # Note: simplistic count for now, optimization might be needed for large datasets
        # total_query = select(func.count()).select_from(query.subquery())
        # total = db.execute(total_query).scalar()
        
        # Order by newest first
        query = query.order_by(desc(SensitiveOperationAudit.created_at))
        
        # Pagination
        query = query.limit(per_page).offset((page - 1) * per_page)
        
        
        results = db.execute(query).scalars().all()
        
        # Convert to dicts to avoid detached instance errors in template
        audit_logs = []
        for log in results:
            user_data = None
            if log.user:
                user_data = {
                    'id': log.user.id,
                    'username': log.user.username
                }
                
            audit_logs.append({
                'id': log.id,
                'created_at': log.created_at,
                'operation_type': log.operation_type,
                'status': log.status,
                'ip_address': log.ip_address,
                'user_id': log.user_id,
                'user': user_data
            })
            
        # Get unique operation types for filter dropdown
        op_types_query = select(SensitiveOperationAudit.operation_type).distinct().order_by(SensitiveOperationAudit.operation_type)
        operation_types = db.execute(op_types_query).scalars().all()
        
        # Prepare safe context variables to override potentially broken context processors in tests
        safe_current_user_has = lambda *roles: False
        unread_count = 0
        
        if attached_user:
            def safe_has_role(*roles):
                return attached_user.has_role(*roles)
            safe_current_user_has = safe_has_role
            
            try:
                from utils.notifications import get_unread_notifications_count_cached
                unread_count = get_unread_notifications_count_cached(attached_user.id)
            except Exception:
                pass

        return render_template(
            "admin/sensitive_operations.html",
            audit_logs=audit_logs,
            page=page,
            operation_types=operation_types,
            current_filters={
                'operation_type': operation_type,
                'status': status,
                'username': username
            },
            current_user=attached_user,
            current_user_has=safe_current_user_has,
            unread_notification_count=unread_count
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
