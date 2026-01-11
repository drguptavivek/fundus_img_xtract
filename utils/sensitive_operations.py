"""
Sensitive Operations Security Utilities

This module provides security controls for sensitive operations such as
database exports, data downloads, and bulk data access.

Reference: docs/PII_Exposure_Control_Policy.md Section 6A.2
Bead: 5N-2 (fundus_img_xtract-43u)
"""

import hashlib
import logging
import os
from datetime import datetime, timedelta
from functools import wraps
from typing import Optional

from flask import request, session, flash, redirect, url_for, render_template, current_app
from flask_login import current_user

from auth.security import verify_password
from auth.utils import utcnow
from db_transaction_manager import get_db_session
from models import User, SensitiveOperationAudit
from utils.log_sanitize import sanitize_log_value

logger = logging.getLogger('sensitive_operations')

# Re-authentication validity window (5 minutes)
REAUTH_VALIDITY_MINUTES = 5


def requires_reauth(operation_name: str):
    """
    Decorator requiring re-authentication for sensitive operations.
    
    This decorator ensures that users must re-enter their password before
    performing sensitive operations like database exports. The re-authentication
    is valid for 5 minutes.
    
    Args:
        operation_name: Name of the operation being protected
    
    Returns:
        Decorated function that requires password re-confirmation
    
    Example:
        @requires_reauth("database_dump")
        @roles_required("admin")
        def database_dump():
            # ... sensitive operation ...
    
    Reference: docs/PII_Exposure_Control_Policy.md Section 6A.2
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Check if user is authenticated
            if not current_user.is_authenticated:
                flash("You must be logged in to perform this operation.", "danger")
                return redirect(url_for('auth.login'))
            
            # Check if recently re-authenticated
            last_reauth = session.get('last_reauth_time')
            if last_reauth:
                try:
                    last_reauth_dt = datetime.fromisoformat(last_reauth)
                    # Make timezone-aware if needed
                    if last_reauth_dt.tzinfo is None:
                        from datetime import timezone
                        last_reauth_dt = last_reauth_dt.replace(tzinfo=timezone.utc)
                    
                    if utcnow() - last_reauth_dt < timedelta(minutes=REAUTH_VALIDITY_MINUTES):
                        # Re-auth still valid, proceed with operation
                        return f(*args, **kwargs)
                except (ValueError, TypeError):
                    # Invalid timestamp, require re-auth
                    pass
            
            # Handle POST with password confirmation
            if request.method == 'POST' and 'confirm_password' in request.form:
                password = request.form.get('confirm_password')
                
                with get_db_session() as db:
                    user = db.get(User, current_user.id)
                    
                    if user and verify_password(password, user.password_hash):
                        # Password verified - update session
                        session['last_reauth_time'] = utcnow().isoformat()
                        
                        # Log successful re-authentication
                        _log_sensitive_operation(
                            operation=operation_name,
                            status='reauth_success',
                            details={'ip': request.remote_addr}
                        )
                        
                        logger.info(
                            "User %s successfully re-authenticated for %s",
                            sanitize_log_value(current_user.username),
                            sanitize_log_value(operation_name)
                        )
                        
                        # Proceed with the original operation
                        return f(*args, **kwargs)
                    else:
                        # Password verification failed
                        _log_sensitive_operation(
                            operation=operation_name,
                            status='reauth_failed',
                            details={'ip': request.remote_addr}
                        )
                        
                        logger.warning(
                            "Failed re-authentication attempt for %s by user %s from IP %s",
                            sanitize_log_value(operation_name),
                            sanitize_log_value(current_user.username),
                            sanitize_log_value(request.remote_addr)
                        )
                        
                        flash("Password verification failed. Please try again.", "danger")
            
            # Show re-authentication form
            return render_template(
                'admin/reauth_confirm.html',
                operation_name=operation_name,
                return_url=request.url
            )
        
        return decorated_function
    return decorator


def _log_sensitive_operation(
    operation: str,
    status: str,
    details: Optional[dict] = None,
    result: Optional[dict] = None
) -> int:
    """
    Log a sensitive operation to the audit table.
    
    Args:
        operation: Type of operation (e.g., 'database_dump')
        status: Status of operation (e.g., 'initiated', 'completed', 'failed')
        details: Optional request details (filters, parameters, etc.)
        result: Optional result details (row_count, file_hash, etc.)
    
    Returns:
        ID of the created audit record
    
    Reference: docs/PII_Exposure_Control_Policy.md Section 6A.3
    """
    try:
        with get_db_session() as db:
            audit = SensitiveOperationAudit(
                user_id=current_user.id if current_user.is_authenticated else None,
                operation_type=operation,
                status=status,
                ip_address=request.remote_addr if request else None,
                user_agent=request.headers.get('User-Agent', '')[:500] if request else None,
            )
            
            if details:
                audit.set_request_details(details)
            
            if result:
                audit.set_result_details(result)
            
            db.add(audit)
            db.commit()
            
            logger.info(
                "Logged sensitive operation: %s, status: %s, user: %s",
                sanitize_log_value(operation),
                sanitize_log_value(status),
                sanitize_log_value(current_user.username if current_user.is_authenticated else 'anonymous')
            )
            
            return audit.id
    except Exception as e:
        logger.error(
            "Failed to log sensitive operation: %s",
            sanitize_log_value(e)
        )
        return -1


def log_export_initiated(
    operation: str,
    filters: Optional[dict] = None
) -> int:
    """
    Log the initiation of an export operation.
    
    Args:
        operation: Type of export operation
        filters: Optional filters/parameters used
    
    Returns:
        Audit record ID
    """
    return _log_sensitive_operation(
        operation=operation,
        status='initiated',
        details=filters
    )


def log_export_completed(
    operation: str,
    file_path: str,
    row_count: int
) -> None:
    """
    Log export completion with file hash for integrity verification.
    
    Args:
        operation: Type of export operation
        file_path: Path to the exported file
        row_count: Number of rows/records exported
    
    Reference: docs/PII_Exposure_Control_Policy.md Section 6A.3
    """
    try:
        # Calculate file hash
        with open(file_path, 'rb') as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()
        
        file_size = os.path.getsize(file_path)
        
        _log_sensitive_operation(
            operation=operation,
            status='completed',
            result={
                'row_count': row_count,
                'file_hash': file_hash,
                'file_size': file_size,
            }
        )
        
        logger.info(
            "Export completed: %s, rows: %s, size: %s bytes, hash: %s",
            sanitize_log_value(operation),
            sanitize_log_value(row_count),
            sanitize_log_value(file_size),
            sanitize_log_value(file_hash[:16])  # Log first 16 chars of hash
        )
    except Exception as e:
        logger.error(
            "Failed to log export completion: %s",
            sanitize_log_value(e)
        )


def log_export_failed(
    operation: str,
    error_message: str
) -> None:
    """
    Log export failure.
    
    Args:
        operation: Type of export operation
        error_message: Error message describing the failure
    """
    _log_sensitive_operation(
        operation=operation,
        status='failed',
        result={'error': error_message}
    )
    
    logger.error(
        "Export failed: %s, error: %s",
        sanitize_log_value(operation),
        sanitize_log_value(error_message)
    )
