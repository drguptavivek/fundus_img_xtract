import pytest
from flask import url_for
from datetime import datetime, timedelta, timezone
from models import SensitiveOperationAudit
from utils.sensitive_operations import REAUTH_VALIDITY_MINUTES

def test_database_dump_requires_reauth(app, client, admin_user):
    """
    Verify that accessing database dump requires re-authentication
    if the session is stale.
    """
    app.config['SERVER_NAME'] = 'localhost'
    with app.app_context():
        # Login as admin (without fresh re-auth)
        with client.session_transaction() as sess:
            sess['user_id'] = admin_user.id
            sess['_user_id'] = str(admin_user.id)
            sess['_fresh'] = True
            # Explicitly set last_reauth_time to be old
            # Use aware UTC time to match server expectations
            now = datetime.now(timezone.utc)
            sess['last_reauth_time'] = (now - timedelta(minutes=REAUTH_VALIDITY_MINUTES + 1)).isoformat()
        
        # Access dump route
        target_url = url_for('admin.database_dump')
        response = client.get(target_url)
        
        assert response.status_code == 200
        # Verify valid re-auth page elements
        assert b"Security Verification" in response.data
        assert b"Authorize and Proceed" in response.data

def test_database_dump_success_after_reauth(app, client, admin_user):
    """
    Verify that database dump proceeds after successful password confirmation
    and logs the operation.
    """
    app.config['SERVER_NAME'] = 'localhost'
    with app.app_context():
        # Setup session without fresh re-auth
        with client.session_transaction() as sess:
            sess['user_id'] = admin_user.id
            sess['_user_id'] = str(admin_user.id)
            sess['_fresh'] = True
            
        target_url = url_for('admin.database_dump')
        
        data = {
            'confirm_password': 'Test@2026', 
        }
        
        # Mock verify_password to ensure success despite env hash issues
        from unittest.mock import patch
        with patch('utils.sensitive_operations.verify_password', return_value=True):
            # Perform POST to confirm password
            response = client.post(target_url, data=data, follow_redirects=True)
        
        assert b"Password verification failed" not in response.data
        
        # Verify Audit Logs
        from db_transaction_manager import get_db_session
        with get_db_session() as db:
            # Check for reauth_success log
            reauth_log = db.query(SensitiveOperationAudit).filter_by(
                operation_type='database_dump',
                status='reauth_success',
                user_id=admin_user.id
            ).first()
            assert reauth_log is not None
            
            # Check for export initiated log
            init_log = db.query(SensitiveOperationAudit).filter_by(
                operation_type='database_dump',
                status='initiated',
                user_id=admin_user.id
            ).first()
            assert init_log is not None

def test_database_excel_export_flow(app, client, admin_user):
    """
    Verify the full flow of Excel export including re-auth and audit logging.
    """
    app.config['SERVER_NAME'] = 'localhost'
    with app.app_context():
        # Pre-set a valid re-auth session
        with client.session_transaction() as sess:
            sess['user_id'] = admin_user.id
            sess['_user_id'] = str(admin_user.id)
            sess['_fresh'] = True
            sess['last_reauth_time'] = datetime.now(timezone.utc).isoformat()
            
        target_url = url_for('admin.database_excel_export')
        
        # 1. GET request - verify access granted
        response = client.get(target_url)
        assert response.status_code == 200
        assert b"Database Excel Export" in response.data
        
        # 2. POST request - perform export of a small table
        data = {
            'tables': ['roles'],
        }
        
        response = client.post(target_url, data=data)
        
        assert response.status_code == 200
        assert response.headers['Content-Type'] == 'application/zip'
        
        # Verify Audit Logs
        from db_transaction_manager import get_db_session
        with get_db_session() as db:
            # Check for 'initiated' with details
            init_log = db.query(SensitiveOperationAudit).filter_by(
                operation_type='database_excel_export',
                status='initiated',
                user_id=admin_user.id
            ).order_by(SensitiveOperationAudit.created_at.desc()).first()
            
            assert init_log is not None
            details = init_log.get_request_details()
            assert details is not None
            assert 'roles' in details.get('tables', [])
            
            # Check for 'completed'
            comp_log = db.query(SensitiveOperationAudit).filter_by(
                operation_type='database_excel_export',
                status='completed',
                user_id=admin_user.id
            ).order_by(SensitiveOperationAudit.created_at.desc()).first()
            
            assert comp_log is not None

def test_database_dump_reauth_expiry(app, client, admin_user):
    """
    Verify that re-auth expires after the validity window.
    """
    app.config['SERVER_NAME'] = 'localhost'
    with app.app_context():
        with client.session_transaction() as sess:
            sess['user_id'] = admin_user.id
            sess['_user_id'] = str(admin_user.id)
            sess['_fresh'] = True
            # Set time just past validity
            expired_time = datetime.now(timezone.utc) - timedelta(minutes=REAUTH_VALIDITY_MINUTES + 1)
            sess['last_reauth_time'] = expired_time.isoformat()
            
        target_url = url_for('admin.database_dump')
        response = client.get(target_url)
        
        # Should ask for password again
        assert b"Security Verification" in response.data
