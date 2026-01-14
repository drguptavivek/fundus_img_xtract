import pytest
import time
from flask import session, url_for
from datetime import datetime
from auth.security import verify_password
from unittest.mock import patch


def test_reauth_redirects_when_stale(app, client, admin_user):
    """Verify that accessing a protected route redirects to confirm-password when session is stale."""
    # We need a dummy protected route for testing
    @app.route('/test-reauth-protected')
    def protected_route():
        from auth.decorators import reauth_required
        @reauth_required(timeout=10) # Short timeout for testing
        def _wrapper():
            return "Sensitive Data"
        return _wrapper()

    with client.session_transaction() as sess:
        sess['_user_id'] = str(admin_user.id) # Flask-Login uses _user_id as string
        sess['_fresh'] = True
        # Set last_sudo_time to be stale (older than 10 seconds)
        sess['last_sudo_time'] = int(time.time()) - 20 

    response = client.get('/test-reauth-protected')
    
    # Should redirect to confirmation page
    assert response.status_code == 302
    assert '/confirm-password' in response.headers['Location']
    assert 'next=' in response.headers['Location']
    assert 'test-reauth-protected' in response.headers['Location']

def test_reauth_allows_when_fresh(app, client, admin_user):
    """Verify that access is allowed when last_sudo_time is fresh."""
    @app.route('/test-reauth-fresh')
    def protected_route():
        from auth.decorators import reauth_required
        @reauth_required(timeout=600)
        def _wrapper():
            return "Sensitive Data"
        return _wrapper()

    with client.session_transaction() as sess:
        sess['_user_id'] = str(admin_user.id)
        sess['_fresh'] = True
        # Set last_sudo_time to now
        sess['last_sudo_time'] = int(time.time())

    response = client.get('/test-reauth-fresh')
    assert response.status_code == 200
    assert b"Sensitive Data" in response.data

def test_confirm_password_updates_session(app, client, admin_user):
    """Verify that confirming password updates last_sudo_time and redirects back."""
    # Start with stale session
    with client.session_transaction() as sess:
        sess['_user_id'] = str(admin_user.id)
        sess['_fresh'] = True
        sess['last_sudo_time'] = int(time.time()) - 3600

    # Submit valid password
    # admin_user fixture usually has password 'password'
    
    # Submit valid password
    
    with app.test_request_context():
        target_url = url_for('auth.confirm_password')
    
    response = client.post(target_url, data={
        'confirm_password': 'Test@2026', # Correct fixture password
        'next': '/dashboard'
    }, follow_redirects=False)

    if response.status_code != 302:
         print(f"DEBUG: Status {response.status_code}, Body: {response.get_data(as_text=True)}")

    assert response.status_code == 302
    assert response.headers['Location'].endswith('/dashboard')
    
    # Verify session updated
    with client.session_transaction() as sess:
        assert sess['last_sudo_time'] > int(time.time()) - 10 # Updated recently

def test_confirm_password_rejects_invalid(app, client, admin_user):
    """Verify that invalid password does not update session."""
    initial_time = int(time.time()) - 3600
    with client.session_transaction() as sess:
        sess['_user_id'] = str(admin_user.id)
        sess['_fresh'] = True
        sess['last_sudo_time'] = initial_time

    with app.test_request_context():
        target_url = url_for('auth.confirm_password')

    response = client.post(target_url, data={
        'confirm_password': 'wrongpassword',
        'next': '/dashboard'
    }, follow_redirects=True)

    assert response.status_code == 200 # Renders template with error
    assert b"Invalid password" in response.data
    
    # Verify session NOT updated
    with client.session_transaction() as sess:
        assert sess['last_sudo_time'] == initial_time
