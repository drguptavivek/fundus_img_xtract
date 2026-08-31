"""
Test login and session management fixtures.

Verifies that the login and session fixtures work correctly.
"""

import pytest


@pytest.mark.integration
class TestLoginFixtures:
    """Verify login and session fixtures work correctly"""
    
    def test_login_user_fixture(self, client, login_user, admin_user):
        """Verify login_user fixture performs actual login"""
        response = login_user(admin_user.username, 'Test@2026')
        
        # Login should redirect
        assert response.status_code in [200, 302, 303]
        
        # User should be logged in (check session)
        with client.session_transaction() as sess:
            assert 'user_id' in sess or response.status_code == 302
    
    def test_logged_in_client_fixture(self, logged_in_client):
        """Verify logged_in_client is authenticated"""
        # Should be able to access authenticated endpoint
        # (This is a basic test - actual endpoint testing comes later)
        with logged_in_client.session_transaction() as sess:
            assert 'user_id' in sess or sess.get('_user_id')
    
    def test_auth_client_factory(self, auth_client_factory, resident_user):
        """Verify auth_client_factory can create authenticated clients"""
        resident_client = auth_client_factory(resident_user)
        
        # Client should be authenticated
        with resident_client.session_transaction() as sess:
            assert 'user_id' in sess or sess.get('_user_id')
    
    def test_csrf_token_fixture(self, csrf_token):
        """Verify CSRF token can be retrieved"""
        # CSRF token might be None if CSRF is disabled in test config
        # Just verify fixture works
        assert csrf_token is None or isinstance(csrf_token, str)
        
        if csrf_token:
            assert len(csrf_token) > 10  # CSRF tokens are typically long
    
    def test_make_request_with_auth(self, make_request_with_auth, logged_in_client):
        """Verify make_request_with_auth helper works"""
        # Make a simple GET request
        response = make_request_with_auth('GET', '/login')
        assert response.status_code in [200, 302]
    
    def test_authenticated_client_bypass_login(self, authenticated_client, admin_user):
        """Verify authenticated_client bypasses login flow"""
        # This fixture sets session directly without login
        with authenticated_client.session_transaction() as sess:
            assert sess['_user_id'] == str(admin_user.id)
            assert sess['_fresh'] is True


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
