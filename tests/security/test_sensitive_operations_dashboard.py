
import pytest
from unittest.mock import MagicMock, patch
from models import SensitiveOperationAudit, User
from utils.sensitive_operations import _log_sensitive_operation
from datetime import datetime


def test_sensitive_operation_logging_masks_pii(db_session, app):
    """
    Verify that PII is masked when logging sensitive operations.
    This tests the _log_sensitive_operation function directly.
    """
    # Create a test user
    user = User(
        username="test_admin",
        email="admin@example.com",
        password_hash="dummy_hash"
    )
    db_session.add(user)
    db_session.flush()
    
    # Use Flask test request context
    with app.test_request_context('/', headers={'User-Agent': 'Test User Agent'}):
        # Mock current_user
        with patch('utils.sensitive_operations.current_user') as mock_user:
            
            mock_user.is_authenticated = True
            mock_user.id = user.id
            mock_user.username = "test_admin"
            
            # Log operation with PII in details
            details_with_pii = {
                "filter": "patient_name=John Doe",
                "email": "patient@example.com",
                "filename": "export_patient_data.csv",
                "nested": {
                    "user_email": "doctor@hospital.com"
                }
            }
            
            result_with_pii = {
                "file": "patient_export_2024.zip",
                "row_count": 100,
                "file_hash": "abc123def456",
                "file_size": 1024
            }
            
            audit_id = _log_sensitive_operation(
                operation="test_export",
                status="completed",
                details=details_with_pii,
                result=result_with_pii
            )
            
            # Refresh session to see committed data from _log_sensitive_operation
            db_session.expire_all()
            
            # Retrieve the audit log
            audit = db_session.get(SensitiveOperationAudit, audit_id)
            assert audit is not None
            
            # Verify request details are sanitized
            request_details = audit.get_request_details()
            assert request_details is not None
            
            # Debug: Print what we got
            print(f"\nDEBUG: request_details = {request_details}")
            print(f"DEBUG: request_details type = {type(request_details)}")
            
            # PII should be masked
            assert "John Doe" not in str(request_details)
            assert "patient@example.com" not in str(request_details)
            assert "doctor@hospital.com" not in str(request_details)
            
            # Emails should be masked (check for masked format)
            assert "pa***@example.com" in str(request_details) or "[EMAIL]" in str(request_details)
            
            # Filename with PII should be masked
            assert "export_patient_data.csv" not in str(request_details)
            assert "[MASKED_FILE]" in str(request_details)
            
            # Verify result details preserve important fields
            result_details = audit.get_result_details()
            assert result_details is not None
            assert result_details["row_count"] == 100
            assert result_details["file_hash"] == "abc123def456"
            assert result_details["file_size"] == 1024
            
            # But filename should be masked
            assert "patient_export_2024.zip" not in str(result_details)
            assert "[MASKED_FILE].zip" in str(result_details)


def test_sensitive_operation_preserves_uuid_filenames(db_session, app):
    """
    Verify that UUID-based filenames are preserved (they don't contain PII).
    """
    user = User(
        username="test_admin",
        email="admin@example.com",
        password_hash="dummy_hash"
    )
    db_session.add(user)
    db_session.flush()
    
    with app.test_request_context('/', headers={'User-Agent': 'Test User Agent'}):
        with patch('utils.sensitive_operations.current_user') as mock_user:
            
            mock_user.is_authenticated = True
            mock_user.id = user.id
            
            # UUID filename (safe, should be preserved)
            result_with_uuid = {
                "file": "a1b2c3d4-e5f6-7890-abcd-ef1234567890.zip",
                "row_count": 50
            }
            
            audit_id = _log_sensitive_operation(
                operation="test_export",
                status="completed",
                result=result_with_uuid
            )
            
            # Refresh session to see committed data
            db_session.expire_all()
            
            audit = db_session.get(SensitiveOperationAudit, audit_id)
            result_details = audit.get_result_details()
            
            # UUID filename should be preserved
            assert result_details["file"] == "a1b2c3d4-e5f6-7890-abcd-ef1234567890.zip"
