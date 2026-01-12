
import pytest
from unittest.mock import Mock, patch, MagicMock
from flask import url_for

class TestAuditDashboard:
    """Tests for Sensitive Operations Audit Dashboard."""
    
    @pytest.fixture
    def mock_user_admin(self):
        """Create a mock admin user."""
        user = Mock()
        user.id = 1
        user.username = 'admin'
        user.is_authenticated = True
        user.has_role.return_value = True
        # Mock role check for decorator
        user.roles = [Mock(name='admin')]
        return user

    @pytest.fixture
    def mock_user_regular(self):
        """Create a mock regular user."""
        user = Mock()
        user.id = 2
        user.username = 'user'
        user.is_authenticated = True
        user.has_role.return_value = False
        user.roles = []
        return user

    def test_admin_can_access_dashboard(self, client, mock_user_admin):
        """Admin user should be able to access the dashboard."""
        with patch('flask_login.utils._get_user', return_value=mock_user_admin):
            with patch('admin.audit_routes.get_db_session') as mock_db:
                # Mock DB session and query results
                mock_session = MagicMock()
                mock_db.return_value.__enter__.return_value = mock_session
                
                # Mock query execution
                mock_session.execute.return_value.scalars.return_value.all.return_value = []
                
                response = client.get('/admin/sensitive-operations')
                assert response.status_code == 200
                assert b'Sensitive Operations Audit' in response.data

    def test_non_admin_cannot_access_dashboard(self, client, mock_user_regular):
        """Non-admin user should be denied access."""
        with patch('flask_login.utils._get_user', return_value=mock_user_regular):
            response = client.get('/admin/sensitive-operations')
            # Should redirect to homepage or login, or return 403 depending on implementation
            # Since @roles_required usually redirects with flash message
            assert response.status_code == 302 

    def test_audit_details_ajax(self, client, mock_user_admin):
        """Admin should be able to fetch audit details via AJAX."""
        with patch('flask_login.utils._get_user', return_value=mock_user_admin):
            with patch('admin.audit_routes.get_db_session') as mock_db:
                mock_session = MagicMock()
                mock_db.return_value.__enter__.return_value = mock_session
                
                # Mock a log entry
                mock_log = Mock()
                mock_log.id = 1
                mock_log.operation_type = 'test_op'
                mock_log.status = 'completed'
                mock_log.user.username = 'testuser'
                mock_log.ip_address = '127.0.0.1'
                from datetime import datetime
                mock_log.created_at = datetime.now()
                mock_log.get_request_details.return_value = {'foo': 'bar'}
                mock_log.get_result_details.return_value = {'rows': 10}
                
                mock_session.get.return_value = mock_log
                
                response = client.get('/admin/sensitive-operations/1')
                assert response.status_code == 200
                data = response.get_json()
                assert data['operation_type'] == 'test_op'
                assert data['request_details'] == {'foo': 'bar'}

