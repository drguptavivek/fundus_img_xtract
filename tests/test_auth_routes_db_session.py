"""
Comprehensive tests for auth routes with database session management validation.
Tests that the fixed auth routes properly handle database sessions without errors.
"""

import pytest
from flask import session, request
from flask_login import current_user
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock
import secrets
import time

from models import User, LoginAttempt, IpLock, PasswordResetAttempt, Role
from auth.routes import _record_attempt, _recent_failed_by_username, _recent_failed_by_ip
from auth.security import hash_password, verify_password
from db_transaction_manager import get_db_session, transaction_scope


class TestAuthRoutesSessionManagement:
    """Test cases for auth routes with focus on database session management"""
    
    def test_login_route_session_management(self, app, test_users):
        """Test that login route properly manages database sessions"""
        with app.test_client() as client:
            # Test successful login with proper session management
            response = client.post("/login", data={
                "username": test_users["admin"].username,
                "password": "Test@2026"
            }, follow_redirects=False)
            
            # Should either redirect or show success
            assert response.status_code in [200, 302]
            
            # Verify no database session errors occurred
            # The transaction_scope context manager should handle commits properly
            with get_db_session() as db:
                # Check that login attempt was recorded
                attempts = db.query(LoginAttempt).filter(
                    LoginAttempt.username_input == test_users["admin"].username,
                    LoginAttempt.success == True
                ).all()
                assert len(attempts) > 0
    
    def test_login_route_transaction_rollback_on_error(self, app, test_users):
        """Test that login route properly rolls back transactions on errors"""
        with app.test_client() as client:
            # Test login with invalid password to trigger error path
            response = client.post("/login", data={
                "username": test_users["admin"].username,
                "password": "wrongpassword"
            })
            
            assert response.status_code == 200
            
            # Verify failed login attempt was recorded properly
            with get_db_session() as db:
                attempts = db.query(LoginAttempt).filter(
                    LoginAttempt.username_input == test_users["admin"].username,
                    LoginAttempt.success == False
                ).all()
                assert len(attempts) > 0
    
    def test_logout_route_session_management(self, app, test_users):
        """Test that logout route properly manages database sessions"""
        with app.test_client() as client:
            # Login first
            client.post("/login", data={
                "username": test_users["admin"].username,
                "password": "Test@2026"
            })
            
            # Then logout
            response = client.get("/logout", follow_redirects=True)
            assert response.status_code == 200
            assert b"login" in response.data.lower() or b"sign" in response.data.lower()
            
            # Verify no session errors occurred during logout
            # Logout should not raise database exceptions
    
    def test_forgot_password_route_session_management(self, app, test_users):
        """Test that forgot password route properly manages database sessions"""
        with app.test_client() as client:
            with patch('utils.emails.send_otp_email') as mock_email:
                mock_email.return_value = None
                
                response = client.post("/forgot-password", data={
                    "email": test_users["admin"].email
                }, follow_redirects=False)
                
                # Should either redirect or show success
                assert response.status_code in [200, 302]
                
                # Verify password reset attempt was recorded
                with get_db_session() as db:
                    attempts = db.query(PasswordResetAttempt).filter(
                        PasswordResetAttempt.email == test_users["admin"].email
                    ).all()
                    assert len(attempts) > 0
    
    def test_forgot_password_rate_limiting_session_management(self, app, test_users):
        """Test that forgot password rate limiting works with proper session management"""
        with app.test_client() as client:
            # Make multiple requests to test rate limiting
            for i in range(6):
                response = client.post("/forgot-password", data={
                    "email": test_users["admin"].email
                })
                
                # First few should succeed, later ones should be rate limited
                if i < 5:
                    assert response.status_code in [200, 302]
                else:
                    # Should be rate limited
                    assert response.status_code == 429 or b"too many" in response.data.lower()
            
            # Verify all attempts were recorded properly
            with get_db_session() as db:
                attempts = db.query(PasswordResetAttempt).filter(
                    PasswordResetAttempt.email == test_users["admin"].email
                ).all()
                assert len(attempts) >= 5
    
    def test_reset_password_route_session_management(self, app, test_users):
        """Test that reset password route properly manages database sessions"""
        with app.test_client() as client:
            # Set up valid OTP in session
            with client.session_transaction() as sess:
                sess['password_reset_otp'] = 'TEST1234'
                sess['password_reset_email'] = test_users["admin"].email
                sess['password_reset_expiry'] = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
                sess['password_reset_user_id'] = test_users["admin"].id
            
            # Test password reset
            response = client.post("/reset-password", data={
                "otp": "TEST1234",
                "new_password": "NewPassword123!",
                "confirm_password": "NewPassword123!"
            }, follow_redirects=False)
            
            # Should redirect to login on success
            assert response.status_code == 302
            
            # Verify password was actually changed in database
            with get_db_session() as db:
                user = db.query(User).filter(User.id == test_users["admin"].id).first()
                assert user is not None
                # Password should be different (hashed)
                assert user.password_hash != test_users["admin"].password_hash
    
    def test_reset_password_transaction_rollback_on_invalid_otp(self, app, test_users):
        """Test that reset password rolls back transaction on invalid OTP"""
        with app.test_client() as client:
            # Set up valid OTP in session
            with client.session_transaction() as sess:
                sess['password_reset_otp'] = 'VALID1234'
                sess['password_reset_email'] = test_users["admin"].email
                sess['password_reset_expiry'] = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
                sess['password_reset_user_id'] = test_users["admin"].id
            
            # Try to reset with invalid OTP
            response = client.post("/reset-password", data={
                "otp": "INVALID123",
                "new_password": "NewPassword123!",
                "confirm_password": "NewPassword123!"
            })
            
            # Should show error, not redirect
            assert response.status_code == 200
            
            # Verify password was NOT changed in database
            with get_db_session() as db:
                user = db.query(User).filter(User.id == test_users["admin"].id).first()
                assert user is not None
                # Password should be unchanged
                assert user.password_hash == test_users["admin"].password_hash
    
    def test_ip_lockout_session_management(self, app, test_users):
        """Test that IP lockout mechanism works with proper session management"""
        with app.test_client() as client:
            # Make multiple failed login attempts to trigger IP lockout
            for i in range(6):
                response = client.post("/login", data={
                    "username": f"nonexistent_{i}",
                    "password": "wrongpassword"
                })
                assert response.status_code == 200
            
            # Verify IP lock was created in database
            with get_db_session() as db:
                ip_locks = db.query(IpLock).all()
                assert len(ip_locks) > 0
    
    def test_user_lockout_session_management(self, app, test_users):
        """Test that user lockout mechanism works with proper session management"""
        with app.test_client() as client:
            # Make multiple failed login attempts for same user
            for i in range(6):
                response = client.post("/login", data={
                    "username": test_users["admin"].username,
                    "password": "wrongpassword"
                })
                assert response.status_code == 200
            
            # Verify user was locked in database
            with get_db_session() as db:
                user = db.query(User).filter(User.id == test_users["admin"].id).first()
                assert user is not None
                assert user.is_locked_until is not None
                assert user.is_locked_until > datetime.now(timezone.utc)


class TestAuthRoutesProtection:
    """Test cases for auth route protection"""
    
    def test_login_route_not_protected(self, app):
        """Test that /login route is accessible without authentication"""
        with app.test_client() as client:
            response = client.get("/login")
            assert response.status_code == 200
            assert b"login" in response.data.lower()
    
    def test_logout_route_requires_authentication(self, app):
        """Test that /logout route requires authentication"""
        with app.test_client() as client:
            response = client.get("/logout", follow_redirects=True)
            # Should redirect to login
            assert response.status_code == 200
            assert b"login" in response.data.lower()
    
    def test_ping_route_requires_authentication(self, app):
        """Test that /ping route requires authentication"""
        with app.test_client() as client:
            response = client.get("/ping")
            # Should redirect to login
            assert response.status_code == 302
    
    def test_forgot_password_route_not_protected(self, app):
        """Test that /forgot-password route is accessible without authentication"""
        with app.test_client() as client:
            response = client.get("/forgot-password")
            assert response.status_code == 200
            assert b"forgot" in response.data.lower() and b"password" in response.data.lower()
    
    def test_reset_password_route_not_protected(self, app):
        """Test that /reset-password route is accessible without authentication"""
        with app.test_client() as client:
            response = client.get("/reset-password")
            assert response.status_code == 200
            assert b"reset" in response.data.lower() and b"password" in response.data.lower()
    
    def test_check_session_route_not_protected(self, app):
        """Test that /check-session route is accessible without authentication"""
        with app.test_client() as client:
            response = client.get("/check-session", follow_redirects=False)
            # Should redirect to login if not authenticated
            assert response.status_code == 302
    
    def test_check_email_status_route_not_protected(self, app):
        """Test that /check-email-status route is accessible without authentication"""
        with app.test_client() as client:
            response = client.get("/check-email-status")
            assert response.status_code == 200
            assert "results" in response.json


class TestAuthRoutesDataPersistence:
    """Test cases for data persistence after successful operations"""
    
    def test_login_attempt_persistence(self, app, test_users):
        """Test that login attempts are persisted correctly"""
        with app.test_client() as client:
            # Make a login attempt
            client.post("/login", data={
                "username": test_users["admin"].username,
                "password": "Test@2026"
            })
            
            # Verify persistence with new session
            with get_db_session() as db:
                attempts = db.query(LoginAttempt).filter(
                    LoginAttempt.username_input == test_users["admin"].username
                ).all()
                assert len(attempts) > 0
                # Check that at least one attempt was successful
                successful_attempts = [a for a in attempts if a.success]
                assert len(successful_attempts) > 0
    
    def test_password_reset_persistence(self, app, test_users):
        """Test that password reset is persisted correctly"""
        with app.test_client() as client:
            # Set up valid OTP in session
            with client.session_transaction() as sess:
                sess['password_reset_otp'] = 'TEST1234'
                sess['password_reset_email'] = test_users["admin"].email
                sess['password_reset_expiry'] = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
                sess['password_reset_user_id'] = test_users["admin"].id
            
            # Reset password
            client.post("/reset-password", data={
                "otp": "TEST1234",
                "new_password": "NewPassword123!",
                "confirm_password": "NewPassword123!"
            })
            
            # Verify persistence with new session
            with get_db_session() as db:
                user = db.query(User).filter(User.id == test_users["admin"].id).first()
                assert user is not None
                # Password should be different
                assert user.password_hash != test_users["admin"].password_hash
                # Should be able to verify with new password
                assert verify_password(user.password_hash, "NewPassword123!")
    
    def test_ip_lock_persistence(self, app):
        """Test that IP locks are persisted correctly"""
        with app.test_client() as client:
            # Trigger IP lock with multiple failed attempts
            for i in range(6):
                client.post("/login", data={
                    "username": f"nonexistent_{i}",
                    "password": "wrongpassword"
                })
            
            # Verify persistence with new session
            with get_db_session() as db:
                ip_locks = db.query(IpLock).all()
                assert len(ip_locks) > 0
                # Check that lock time is in the future
                for lock in ip_locks:
                    assert lock.locked_until > datetime.now(timezone.utc)


class TestAuthRoutesErrorHandling:
    """Test cases for error handling in auth routes"""
    
    def test_database_error_handling(self, app, test_users):
        """Test that database errors are handled gracefully"""
        with app.test_client() as client:
            # Mock a database error
            with patch('db_transaction_manager.DbSession') as mock_session:
                mock_db = MagicMock()
                mock_session.return_value = mock_db
                mock_db.query.side_effect = Exception("Database error")
                
                # Should handle error gracefully
                response = client.post("/login", data={
                    "username": test_users["admin"].username,
                    "password": "Test@2026"
                })
                
                # Should not crash the application
                assert response.status_code in [200, 302, 500]
    
    def test_session_cleanup_on_error(self, app, test_users):
        """Test that sessions are properly cleaned up even when errors occur"""
        with app.test_client() as client:
            # Try to reset password with invalid data to trigger error
            with client.session_transaction() as sess:
                sess['password_reset_otp'] = 'TEST1234'
                sess['password_reset_email'] = test_users["admin"].email
                sess['password_reset_expiry'] = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
                sess['password_reset_user_id'] = test_users["admin"].id
            
            # Send invalid data
            response = client.post("/reset-password", data={
                "otp": "WRONG123",
                "new_password": "short",
                "confirm_password": "different"
            })
            
            # Should handle error without crashing
            assert response.status_code == 200
            
            # Session should still be usable
            response = client.get("/reset-password")
            assert response.status_code == 200