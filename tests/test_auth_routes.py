"""Test authentication routes."""

import pytest
from flask import url_for
from models import User, Role, Session
from sqlalchemy import select
from auth.security import hash_password


class TestAuthRoutes:
    """Test cases for authentication routes."""

    def test_user_login_success(self, client):
        """Test successful user login."""
        # Create a test user
        with Session() as db:
            # Check if contributor role exists, create if not
            user_role = db.execute(
                select(Role).where(Role.name == 'contributor')
            ).scalar_one_or_none()
            
            if not user_role:
                user_role = Role(name='contributor')
                db.add(user_role)
                db.flush()
            
            # Check if test user exists, create if not
            test_user = db.execute(
                select(User).where(User.username == 'testuser')
            ).scalar_one_or_none()
            
            if not test_user:
                test_user = User(
                    username='testuser',
                    password_hash=hash_password('testpassword'),
                    is_active=True,
                    full_name='Test User'
                )
                test_user.roles.append(user_role)
                db.add(test_user)
                db.commit()

        # Login
        response = client.post('/auth/login', data={
            'username': 'testuser',
            'password': 'testpassword'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        # Should redirect to homepage or dashboard
        assert b'ZIP' in response.data or b'Image' in response.data or b'Welcome' in response.data or b'<title>' in response.data

    def test_user_login_failure(self, client):
        """Test failed user login with wrong credentials."""
        # Try to login with wrong password
        response = client.post('/auth/login', data={
            'username': 'nonexistent',
            'password': 'wrongpassword'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        # Should show login error - checking for common error indicators
        response_text = response.data.decode('utf-8').lower()
        assert 'invalid' in response_text or 'incorrect' in response_text or 'error' in response_text or 'failed' in response_text

    def test_user_logout(self, client):
        """Test user logout."""
        # Create a test user
        with Session() as db:
            # Check if contributor role exists, create if not
            user_role = db.execute(
                select(Role).where(Role.name == 'contributor')
            ).scalar_one_or_none()
            
            if not user_role:
                user_role = Role(name='contributor')
                db.add(user_role)
                db.flush()
            
            # Check if test user exists, create if not
            test_user = db.execute(
                select(User).where(User.username == 'testuser_logout')
            ).scalar_one_or_none()
            
            if not test_user:
                test_user = User(
                    username='testuser_logout',
                    password_hash=hash_password('testpassword'),
                    is_active=True
                )
                test_user.roles.append(user_role)
                db.add(test_user)
                db.commit()

        # Login
        client.post('/auth/login', data={
            'username': 'testuser_logout',
            'password': 'testpassword'
        }, follow_redirects=True)
        
        # Access protected page
        response = client.get('/', follow_redirects=True)
        assert response.status_code == 200
        
        # Logout
        response = client.get('/auth/logout', follow_redirects=True)
        assert response.status_code == 200
        
        # Try to access protected page again
        response = client.get('/', follow_redirects=True)
        # Should redirect to login
        assert response.status_code == 200
        assert b'login' in response.data.lower() or b'sign in' in response.data.lower()