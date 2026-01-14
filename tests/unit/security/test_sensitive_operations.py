"""
Unit tests for Sensitive Operations Security Utilities.

Test IDs from PII_Exposure_Control_Policy.md:
- PII-SEC-001: Non-admin cannot access sensitive operations

Bead: 5N-2 (fundus_img_xtract-43u)
"""

import pytest
from datetime import timedelta
from unittest.mock import Mock, patch, MagicMock

from auth.utils import utcnow
from utils.sensitive_operations import (
    requires_reauth,
    _log_sensitive_operation,
    log_export_initiated,
    log_export_completed,
    log_export_failed,
    REAUTH_VALIDITY_MINUTES
)


class TestRequiresReauth:
    """Tests for @requires_reauth decorator."""

    @pytest.fixture
    def mock_app(self):
        """Create a mock Flask app context with Flask-Login initialized."""
        from flask import Flask
        from flask_login import LoginManager
        app = Flask(__name__)
        app.config['SECRET_KEY'] = 'test-secret-key'
        app.config['TESTING'] = True

        # Initialize Flask-Login (required for current_user proxy to work)
        login_manager = LoginManager()
        login_manager.init_app(app)

        # Add a user_loader callback (required by Flask-Login)
        @login_manager.user_loader
        def _load_user(user_id):
            return None  # Not used in unit tests

        return app

    @pytest.fixture
    def mock_user(self):
        """Create a mock user."""
        user = Mock()
        user.id = 1
        user.username = 'testuser'
        user.password_hash = '$2b$12$test_hash'
        user.is_authenticated = True
        return user

    def test_unauthenticated_user_redirects_to_login(self, mock_app):
        """Unauthenticated users should be redirected to login."""
        with mock_app.test_request_context():
            with patch('utils.sensitive_operations.current_user', new_callable=MagicMock) as mock_current_user:
                mock_current_user.is_authenticated = False

                @requires_reauth("test_operation")
                def test_func():
                    return "success"

                with patch('utils.sensitive_operations.redirect') as mock_redirect:
                    with patch('utils.sensitive_operations.url_for') as mock_url_for:
                        with patch('utils.sensitive_operations.flash') as mock_flash:
                            test_func()

                            mock_flash.assert_called_once()
                            mock_url_for.assert_called_with('auth.login')
                            mock_redirect.assert_called_once()

    def test_recent_reauth_allows_operation(self, mock_app, mock_user):
        """Recently re-authenticated users should proceed without password."""
        with mock_app.test_request_context():
            # Mock utcnow() to have consistent time for comparison
            from auth.utils import utcnow
            now = utcnow()
            recent_time = now - timedelta(minutes=2)

            with patch('utils.sensitive_operations.current_user', new_callable=MagicMock) as mock_current_user:
                mock_current_user.is_authenticated = True
                mock_current_user.id = 1
                mock_current_user.username = 'testuser'

                # Use patch.object to mock Flask's session dict properly
                from flask import session as flask_session
                with patch.dict(flask_session, {'last_reauth_time': recent_time.isoformat()}):
                    # Mock utcnow() to return the same 'now' time
                    with patch('utils.sensitive_operations.utcnow', return_value=now):
                        @requires_reauth("test_operation")
                        def test_func():
                            return "success"

                        result = test_func()
                        assert result == "success"
    
    def test_expired_reauth_requires_password(self, mock_app, mock_user):
        """Expired re-auth should require password confirmation."""
        with mock_app.test_request_context():
            # Mock session.get() to return expired reauth time (10 minutes ago)
            expired_time = utcnow() - timedelta(minutes=10)

            with patch('utils.sensitive_operations.current_user', mock_user):
                with patch('utils.sensitive_operations.session') as mock_session:
                    mock_session.get.return_value = expired_time.isoformat()

                    with patch('utils.sensitive_operations.render_template') as mock_render:
                        @requires_reauth("test_operation")
                        def test_func():
                            return "success"

                        test_func()

                        mock_render.assert_called_once()
                        args, kwargs = mock_render.call_args
                        assert args[0] == 'admin/reauth_confirm.html'
                        assert kwargs['operation_name'] == 'test_operation'
    
    def test_correct_password_proceeds(self, mock_app, mock_user):
        """Correct password should proceed with operation."""
        with mock_app.test_request_context(method='POST', data={'confirm_password': 'correct_password'}):
            with patch('utils.sensitive_operations.current_user', mock_user):
                with patch('utils.sensitive_operations.session') as mock_flask_session:
                    # No previous reauth time - force password check
                    mock_flask_session.get.return_value = None

                    with patch('utils.sensitive_operations.verify_password', return_value=True):
                        with patch('utils.sensitive_operations.get_db_session') as mock_db:
                            mock_db_session = MagicMock()
                            mock_db_session.get.return_value = mock_user
                            mock_db.return_value.__enter__.return_value = mock_db_session

                            with patch('utils.sensitive_operations._log_sensitive_operation'):
                                @requires_reauth("test_operation")
                                def test_func():
                                    return "success"

                                result = test_func()
                                assert result == "success"
    
    def test_incorrect_password_shows_error(self, mock_app, mock_user):
        """Incorrect password should show error and re-auth form."""
        with mock_app.test_request_context(method='POST', data={'confirm_password': 'wrong_password'}):
            with patch('utils.sensitive_operations.current_user', mock_user):
                with patch('utils.sensitive_operations.session') as mock_flask_session:
                    # No previous reauth time - force password check
                    mock_flask_session.get.return_value = None

                    with patch('utils.sensitive_operations.verify_password', return_value=False):
                        with patch('utils.sensitive_operations.get_db_session') as mock_db:
                            mock_db_session = MagicMock()
                            mock_db_session.get.return_value = mock_user
                            mock_db.return_value.__enter__.return_value = mock_db_session

                            with patch('utils.sensitive_operations._log_sensitive_operation'):
                                with patch('utils.sensitive_operations.flash') as mock_flash:
                                    with patch('utils.sensitive_operations.render_template') as mock_render:
                                        @requires_reauth("test_operation")
                                        def test_func():
                                            return "success"

                                        test_func()

                                        mock_flash.assert_called_once()
                                        assert "failed" in mock_flash.call_args[0][0].lower()
                                        mock_render.assert_called_once()


class TestAuditLogging:
    """Tests for audit logging functions."""
    
    @pytest.fixture
    def mock_current_user(self):
        """Create a mock current user."""
        user = Mock()
        user.id = 1
        user.username = 'testuser'
        user.is_authenticated = True
        return user
    
    @pytest.fixture
    def mock_request(self):
        """Create a mock request."""
        req = Mock()
        req.remote_addr = '192.168.1.1'
        req.headers = {'User-Agent': 'TestBrowser/1.0'}
        return req
    
    def test_log_sensitive_operation_creates_audit_record(self, mock_current_user, mock_request):
        """Should create audit record with all details."""
        with patch('utils.sensitive_operations.current_user', mock_current_user):
            with patch('utils.sensitive_operations.request', mock_request):
                with patch('utils.sensitive_operations.get_db_session') as mock_db:
                    mock_session = MagicMock()
                    mock_audit = Mock()
                    mock_audit.id = 123
                    mock_db.return_value.__enter__.return_value = mock_session
                    
                    with patch('utils.sensitive_operations.SensitiveOperationAudit', return_value=mock_audit):
                        audit_id = _log_sensitive_operation(
                            operation='database_dump',
                            status='initiated',
                            details={'table': 'users'},
                            result={'rows': 100}
                        )
                        
                        assert audit_id == 123
                        mock_session.add.assert_called_once_with(mock_audit)
                        mock_session.commit.assert_called_once()
    
    def test_log_export_initiated(self, mock_current_user, mock_request):
        """Should log export initiation with filters."""
        with patch('utils.sensitive_operations.current_user', mock_current_user):
            with patch('utils.sensitive_operations.request', mock_request):
                with patch('utils.sensitive_operations._log_sensitive_operation') as mock_log:
                    filters = {'date_range': '2024-01-01 to 2024-12-31'}
                    log_export_initiated('dataset_export', filters)
                    
                    mock_log.assert_called_once_with(
                        operation='dataset_export',
                        status='initiated',
                        details=filters
                    )
    
    def test_log_export_completed_calculates_hash(self, mock_current_user, mock_request, tmp_path):
        """Should calculate file hash and log completion."""
        # Create a temporary test file
        test_file = tmp_path / "test_export.csv"
        test_file.write_text("test,data\n1,2\n")
        
        with patch('utils.sensitive_operations.current_user', mock_current_user):
            with patch('utils.sensitive_operations.request', mock_request):
                with patch('utils.sensitive_operations._log_sensitive_operation') as mock_log:
                    log_export_completed('csv_export', str(test_file), 2)
                    
                    mock_log.assert_called_once()
                    args, kwargs = mock_log.call_args
                    assert kwargs['operation'] == 'csv_export'
                    assert kwargs['status'] == 'completed'
                    assert 'row_count' in kwargs['result']
                    assert 'file_hash' in kwargs['result']
                    assert 'file_size' in kwargs['result']
                    assert kwargs['result']['row_count'] == 2
    
    def test_log_export_failed(self, mock_current_user, mock_request):
        """Should log export failure with error message."""
        with patch('utils.sensitive_operations.current_user', mock_current_user):
            with patch('utils.sensitive_operations.request', mock_request):
                with patch('utils.sensitive_operations._log_sensitive_operation') as mock_log:
                    log_export_failed('database_dump', 'Connection timeout')
                    
                    mock_log.assert_called_once_with(
                        operation='database_dump',
                        status='failed',
                        result={'error': 'Connection timeout'}
                    )


class TestReauthValidity:
    """Tests for re-authentication validity window."""
    
    def test_reauth_validity_is_5_minutes(self):
        """Re-auth validity should be 5 minutes."""
        assert REAUTH_VALIDITY_MINUTES == 5
