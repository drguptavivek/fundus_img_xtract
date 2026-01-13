import pytest
from flask import url_for
from bs4 import BeautifulSoup

def test_reauth_ui_elements(app, client, admin_user):
    """
    Verify that the re-auth confirmation page contains all the new UI elements
    and is rendered with the correct context.
    
    TDD Verification for Bead ej7.
    """
    # Set SERVER_NAME to allow url_for to work in templates during tests
    app.config['SERVER_NAME'] = 'localhost'
    
    with app.app_context():
        # 1. Login as admin
        with client.session_transaction() as sess:
            sess['user_id'] = admin_user.id
            sess['_user_id'] = str(admin_user.id)
            sess['_fresh'] = True
        
        # 2. Access a route protected by @requires_reauth
        target_url = url_for('admin.database_dump')

        response = client.get(target_url, follow_redirects=True)
        
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        soup = BeautifulSoup(html, 'html.parser')
        
        # 3. Verify Premium UI elements
        assert soup.find(class_='reauth-glass-card') is not None
        assert soup.find(class_='bi-shield-check') is not None
        
        # 4. Verify Password Toggle
        toggle_btn = soup.find(id='password-toggle')
        assert toggle_btn is not None
        assert 'bi-eye-slash' in str(toggle_btn) # Initial state should be hidden
        
        # 5. Verify Countdown Timer
        countdown = soup.find(id='countdown')
        assert countdown is not None
        assert '05:00' in countdown.text
        
        # 6. Verify Operation Context
        operation_pill = soup.find(class_='operation-pill')
        assert operation_pill is not None
        assert "Database Dump" in operation_pill.text
        
        # 7. Verify Form and CSRF
        form = soup.find(id='reauth-form')
        assert form is not None
        assert soup.find('input', dict(name='csrf_token')) is not None
        
        # 8. Verify Submit Button and Spinner
        submit_btn = soup.find(class_='reauth-submit')
        assert submit_btn is not None
        assert soup.find(class_='spinner-border') is not None

def test_reauth_cancel_button(app, client, admin_user):
    """Verify the cancel button points to the admin status page."""
    app.config['SERVER_NAME'] = 'localhost'
    
    with app.app_context():
        with client.session_transaction() as sess:
            sess['user_id'] = admin_user.id
            sess['_user_id'] = str(admin_user.id)
            sess['_fresh'] = True
        
        target_url = url_for('admin.database_dump')
        response = client.get(target_url, follow_redirects=True)
        soup = BeautifulSoup(response.get_data(as_text=True), 'html.parser')
        
        cancel_btn = soup.find('a', string=lambda t: t and 'Cancel' in t)
        assert cancel_btn is not None
        # Check that it points to the admin status page (handle both absolute and relative)
        assert cancel_btn['href'].endswith('/admin/status')
