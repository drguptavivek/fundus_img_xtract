"""
Authentication fixture that uses session-based authentication.

This fixture creates authenticated test clients by directly setting
the Flask-Login session key (_user_id), bypassing the actual /login
POST request to avoid transaction conflicts with test isolation.
"""

import pytest


@pytest.fixture
def auth_client(client, request, db_session):
    """
    Create an authenticated client for a specific user.

    Uses session-based authentication (sets _user_id directly in session)
    to bypass the actual /login POST request. This avoids transaction
    conflicts with the test database isolation strategy.

    Usage:
        def test_something(auth_client, hosp_a_data_manager):
            # Get authenticated client for this user
            authenticated = auth_client(hosp_a_data_manager)

            # Make authenticated requests
            response = authenticated.get('/protected/route')
            assert response.status_code == 200
    """
    def _auth_client(user, password='Test@2026'):
        """
        Authenticate as a specific user and return the client with valid session.

        Uses Flask-Login's session key (_user_id) to establish authentication
        without hitting the actual login endpoint.

        Args:
            user: User object to authenticate as
            password: Password (unused - kept for API compatibility)

        Returns:
            Flask test client with authenticated session
        """
        # Merge session-scoped users into current function-scoped session
        # This is necessary for session-scoped fixtures like master_admin
        try:
            user_id = user.id
        except Exception:
            # User is detached from session, merge it
            user = db_session.merge(user)
            user_id = user.id

        # Set user_id directly in session to authenticate without login POST
        # Flask-Login uses '_user_id' key to identify the logged-in user
        with client.session_transaction() as sess:
            sess['_user_id'] = str(user_id) # DO NOT NAKE IT INTEGER. ThAT casues all tests to fail
            sess['_fresh'] = True  # Mark session as fresh

        return client

    return _auth_client


@pytest.fixture
def multi_auth_clients(client, db_session):
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

        Uses session-based authentication for each user.

        Args:
            users: List of User objects
            password: Password (unused - kept for API compatibility)

        Returns:
            Dict[username -> authenticated client]
        """
        clients = {}

        for user in users:
            # Create a new test client for each user
            user_client = client.application.test_client()

            # Merge session-scoped users into current function-scoped session
            try:
                user_id = user.id
                username = user.username
            except Exception:
                # User is detached from session, merge it
                user = db_session.merge(user)
                user_id = user.id
                username = user.username

            # Set user_id directly in session
            with user_client.session_transaction() as sess:
                sess['_user_id'] = str(user_id)
                sess['_fresh'] = True

            clients[username] = user_client

        return clients

    return _multi_auth_clients
