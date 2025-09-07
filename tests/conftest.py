"""Pytest configuration and fixtures for the Fundus Image Manager."""

import pytest
import os
import sys
import tempfile
from pathlib import Path
# Add the project root to the path so we can import app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from models import Base, engine, Session, User, Role
from sqlalchemy import create_engine, select
from auth.security import hash_password


@pytest.fixture(scope="session")
def app():
    """Create a Flask app instance for testing."""
    # Use the test environment file
    test_env_path = Path(__file__).parent / '.env.test'
    if test_env_path.exists():
        from dotenv import load_dotenv
        load_dotenv(test_env_path)
    
    # Set additional test environment variables
    os.environ['TESTING'] = 'True'
    
    # Create app with test configuration
    app = create_app()
    app.config['TESTING'] = True
    
    with app.app_context():
        # Create all tables
        Base.metadata.create_all(engine)
        yield app


@pytest.fixture
def client(app):
    """Create a test client for the app."""
    return app.test_client()


@pytest.fixture
def runner(app):
    """Create a test CLI runner."""
    return app.test_cli_runner()


@pytest.fixture
def auth_client(client):
    """Create a client with authentication helpers."""
    class AuthActions:
        def __init__(self, client):
            self._client = client

        def login(self, username='test', password='test'):
            return self._client.post(
                '/auth/login',
                data={'username': username, 'password': password}
            )

        def logout(self):
            return self._client.get('/auth/logout')

    return AuthActions(client)


@pytest.fixture
def admin_user():
    """Create an admin user for testing."""
    with Session() as db:
        # Check if admin role exists, create if not
        admin_role = db.execute(
            select(Role).where(Role.name == 'admin')
        ).scalar_one_or_none()
        
        if not admin_role:
            admin_role = Role(name='admin')
            db.add(admin_role)
            db.flush()
        
        # Check if admin user exists, create if not
        admin_user = db.execute(
            select(User).where(User.username == 'admin')
        ).scalar_one_or_none()
        
        if not admin_user:
            admin_user = User(
                username='admin',
                password_hash=hash_password('adminpassword'),
                is_active=True,
                full_name='Test Administrator'
            )
            admin_user.roles.append(admin_role)
            db.add(admin_user)
            db.commit()
        
        return admin_user


@pytest.fixture
def authenticated_admin_client(client, admin_user):
    """Create a test client with an authenticated admin user."""
    # Login as admin
    response = client.post('/auth/login', data={
        'username': 'admin',
        'password': 'adminpassword'
    }, follow_redirects=True)
    
    assert response.status_code in [200, 302]
    return client


@pytest.fixture(scope="session")
def setup_test_data():
    """Setup test data including master data and users."""
    # This fixture will be implemented in a separate module
    pass