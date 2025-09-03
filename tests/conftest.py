import pytest
import os
import tempfile
from app import create_app
from models import Base, engine, Session, User, Role
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
import tempfile
from pathlib import Path
from auth.security import hash_password


@pytest.fixture
def app():
    """Create a Flask app instance for testing."""
    # Create a temporary directory for the test database
    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    
    # Set environment variables for testing
    os.environ['DATABASE_URL'] = f'sqlite:///{db_path}'
    os.environ['TESTING'] = 'True'
    
    app = create_app()
    app.config['TESTING'] = True
    
    with app.app_context():
        # Create all tables
        Base.metadata.create_all(engine)
        yield app
    
    # Cleanup
    os.close(db_fd)
    os.unlink(db_path)


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
        
        # Create admin user
        admin_user = User(
            username='admin',
            password_hash=hash_password('adminpassword'),
            is_active=True
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