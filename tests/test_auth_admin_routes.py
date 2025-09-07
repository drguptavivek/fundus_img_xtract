"""Test authentication and admin routes."""

import pytest
from flask import url_for
from models import User, Role, Session, Hospital, LabUnit
from sqlalchemy import select
from auth.security import hash_password


class TestAuthRoutes:
    """Test cases for authentication routes."""

    def test_user_login_success(self, client):
        """Test successful user login."""
        # Create a test user
        with Session() as db:
            user_role = Role(name='contributor')
            db.add(user_role)
            db.flush()
            
            test_user = User(
                username='testuser_auth',
                password_hash=hash_password('testpassword'),
                is_active=True,
                full_name='Test User Auth'
            )
            test_user.roles.append(user_role)
            db.add(test_user)
            db.commit()

        # Login
        response = client.post('/auth/login', data={
            'username': 'testuser_auth',
            'password': 'testpassword'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        # Should redirect to homepage
        assert b'ZIP' in response.data or b'Image' in response.data

    def test_user_login_failure(self, client):
        """Test failed user login with wrong credentials."""
        # Try to login with wrong password
        response = client.post('/auth/login', data={
            'username': 'nonexistent',
            'password': 'wrongpassword'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        # Should show login error
        assert b'Invalid username or password' in response.data.lower()

    def test_user_logout(self, client, auth_client):
        """Test user logout."""
        # Create a test user
        with Session() as db:
            user_role = Role(name='contributor')
            db.add(user_role)
            db.flush()
            
            test_user = User(
                username='testuser_logout',
                password_hash=hash_password('testpassword'),
                is_active=True
            )
            test_user.roles.append(user_role)
            db.add(test_user)
            db.commit()

        # Login
        auth_client.login('testuser_logout', 'testpassword')
        
        # Access protected page
        response = client.get('/')
        assert response.status_code == 200
        
        # Logout
        response = auth_client.logout()
        assert response.status_code in [200, 302]
        
        # Try to access protected page again
        response = client.get('/')
        # Should redirect to login
        assert response.status_code == 302


class TestAdminAuthRoutes:
    """Test cases for admin authentication routes."""

    def test_admin_login_required(self, client):
        """Test that admin routes require login."""
        response = client.get('/admin/users')
        # Should redirect to login
        assert response.status_code == 302
        assert '/login' in response.location

    def test_admin_role_required(self, client, auth_client):
        """Test that admin routes require admin role."""
        # Create a non-admin user
        with Session() as db:
            # Create a regular user role
            user_role = Role(name='contributor')
            db.add(user_role)
            db.flush()
            
            # Create a regular user
            regular_user = User(
                username='regularuser_admin',
                password_hash=hash_password('regularpassword'),
                is_active=True
            )
            regular_user.roles.append(user_role)
            db.add(regular_user)
            db.commit()

        # Login as regular user
        response = auth_client.login('regularuser_admin', 'regularpassword')
        
        # Try to access admin route
        response = client.get('/admin/users')
        # Should show unauthorized or redirect
        assert response.status_code in [403, 302]

    def test_admin_login_success(self, client, auth_client):
        """Test successful admin login."""
        # Create admin user
        with Session() as db:
            admin_role = Role(name='admin')
            db.add(admin_role)
            db.flush()
            
            admin_user = User(
                username='admin_auth',
                password_hash=hash_password('adminpassword'),
                is_active=True,
                full_name='Administrator Auth'
            )
            admin_user.roles.append(admin_role)
            db.add(admin_user)
            db.commit()

        # Login as admin
        response = auth_client.login('admin_auth', 'adminpassword')
        assert response.status_code in [200, 302]
        
        # Try to access admin dashboard
        response = client.get('/admin/users')
        assert response.status_code == 200

    def test_admin_logout(self, client, auth_client):
        """Test admin logout."""
        # Create admin user
        with Session() as db:
            admin_role = Role(name='admin')
            db.add(admin_role)
            db.flush()
            
            admin_user = User(
                username='admin_logout',
                password_hash=hash_password('adminpassword'),
                is_active=True
            )
            admin_user.roles.append(admin_role)
            db.add(admin_user)
            db.commit()

        # Login
        auth_client.login('admin_logout', 'adminpassword')
        
        # Access protected route
        response = client.get('/admin/users')
        assert response.status_code == 200
        
        # Logout
        response = auth_client.logout()
        assert response.status_code in [200, 302]
        
        # Try to access protected route again
        response = client.get('/admin/users')
        # Should redirect to login
        assert response.status_code == 302
        assert '/login' in response.location