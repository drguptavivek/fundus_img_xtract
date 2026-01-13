"""
Authentication fixture that performs real login and manages cookies.

This fixture creates authenticated test clients by performing actual login
via POST request and maintaining the session cookie for subsequent requests.
"""

import pytest
import os
from pathlib import Path


@pytest.fixture
def auth_client(client, request):
    """
    Create an authenticated client for a specific user.
    
    Usage:
        def test_something(auth_client, hosp_a_data_manager):
            # Get authenticated client for this user
            authenticated = auth_client(hosp_a_data_manager)
            
            # Make authenticated requests
            response = authenticated.get('/protected/route')
            assert response.status_code == 200
    
    The fixture performs actual login via POST and maintains cookies.
    """
    def _auth_client(user, password='Test@2026'):
        """
        Authenticate as a specific user and return the client with valid session.
        
        Args:
            user: User object to authenticate as
            password: Password (default: 'Test@2026')
            
        Returns:
            Flask test client with authenticated session
        """
        # Get CSRF token from login page (if CSRF is enabled)
        login_page = client.get('/login')
        csrf_token = None
        
        if b'csrf_token' in login_page.data:
            import re
            match = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', login_page.data)
            if match:
                csrf_token = match.group(1).decode('utf-8')
        
        # Prepare login data
        data = {
            'username': user.username,
            'password': password,
        }
        if csrf_token:
            data['csrf_token'] = csrf_token
        
        # Perform actual login
        response = client.post(
            '/login',
            data=data,
            follow_redirects=True  # Follow redirects to complete login
        )
        
        # Verify we got a response (login route should return 200 after redirect)
        assert response.status_code == 200, \
            f"Login request failed for {user.username}: {response.status_code}"
        
        # The client now has the session cookie set
        # Flask test client automatically maintains cookies between requests
        return client
    
    return _auth_client


@pytest.fixture
def multi_auth_clients(client):
    """
    Create multiple authenticated clients for different users.
    
    Usage:
        def test_isolation(multi_auth_clients, hosp_a_data_manager, hosp_b_data_manager):
            clients = multi_auth_clients([hosp_a_data_manager, hosp_b_data_manager])
            
            # Use different clients
            response_a = clients[hosp_a_data_manager.username].get('/data')
            response_b = clients[hosp_b_data_manager.username].get('/data')
    
    Returns:
        Dict mapping username to authenticated client
    """
    def _multi_auth_clients(users, password='Test@2026'):
        """
        Create authenticated clients for multiple users.
        
        Args:
            users: List of User objects
            password: Password for all users (default: 'Test@2026')
            
        Returns:
            Dict[username -> authenticated client]
        """
        from flask import Flask
        clients = {}
        
        for user in users:
            # Create a new test client for each user
            # This ensures cookies don't interfere between users
            user_client = client.application.test_client()
            
            # Perform login
            response = user_client.post(
                '/login',
                data={
                    'username': user.username,
                    'password': password,
                },
                follow_redirects=False
            )
            
            assert response.status_code in [200, 302], \
                f"Login failed for {user.username}: {response.status_code}"
            
            clients[user.username] = user_client
        
        return clients
    
    return _multi_auth_clients
