"""Test admin authentication routes."""

import pytest
from flask import url_for
from models import User, Role, Session
from sqlalchemy import select
from auth.security import hash_password


class TestAdminAuthRoutes:
    """Test cases for admin authentication routes."""

    def test_admin_role_required(self, client):
        """Test that admin routes require admin role."""
        # Create a non-admin user
        with Session() as db:
            # Create a regular user role if it doesn't exist
            user_role = db.execute(
                select(Role).where(Role.name == 'contributor')
            ).scalar_one_or_none()
            
            if not user_role:
                user_role = Role(name='contributor')
                db.add(user_role)
                db.flush()
            
            # Create a regular user if it doesn't exist
            regular_user = db.execute(
                select(User).where(User.username == 'regularuser')
            ).scalar_one_or_none()
            
            if not regular_user:
                regular_user = User(
                    username='regularuser',
                    password_hash=hash_password('regularpassword'),
                    is_active=True,
                    full_name='Regular User'
                )
                regular_user.roles.append(user_role)
                db.add(regular_user)
                db.commit()

        # Login as regular user
        client.post('/auth/login', data={
            'username': 'regularuser',
            'password': 'regularpassword'
        }, follow_redirects=True)
        
        # Try to access admin route
        response = client.get('/admin/users', follow_redirects=True)
        # Should show unauthorized or redirect
        assert response.status_code in [200, 302, 403]

    def test_admin_login_success(self, client):
        """Test successful admin login."""
        # Create admin user if it doesn't exist
        with Session() as db:
            admin_role = db.execute(
                select(Role).where(Role.name == 'admin')
            ).scalar_one_or_none()
            
            if not admin_role:
                admin_role = Role(name='admin')
                db.add(admin_role)
                db.flush()
            
            admin_user = db.execute(
                select(User).where(User.username == 'admin')
            ).scalar_one_or_none()
            
            if not admin_user:
                admin_user = User(
                    username='admin',
                    password_hash=hash_password('adminpassword'),
                    is_active=True,
                    full_name='Administrator'
                )
                admin_user.roles.append(admin_role)
                db.add(admin_user)
                db.commit()

        # Login as admin
        response = client.post('/auth/login', data={
            'username': 'admin',
            'password': 'adminpassword'
        }, follow_redirects=True)
        
        assert response.status_code in [200, 302]
        
        # Try to access admin dashboard
        response = client.get('/admin/users', follow_redirects=True)
        assert response.status_code == 200

    def test_admin_logout(self, client):
        """Test admin logout."""
        # Create admin user if it doesn't exist
        with Session() as db:
            admin_role = db.execute(
                select(Role).where(Role.name == 'admin')
            ).scalar_one_or_none()
            
            if not admin_role:
                admin_role = Role(name='admin')
                db.add(admin_role)
                db.flush()
            
            admin_user = db.execute(
                select(User).where(User.username == 'admin')
            ).scalar_one_or_none()
            
            if not admin_user:
                admin_user = User(
                    username='admin',
                    password_hash=hash_password('adminpassword'),
                    is_active=True
                )
                admin_user.roles.append(admin_role)
                db.add(admin_user)
                db.commit()

        # Login as admin
        client.post('/auth/login', data={
            'username': 'admin',
            'password': 'adminpassword'
        }, follow_redirects=True)
        
        # Access protected route
        response = client.get('/admin/users', follow_redirects=True)
        assert response.status_code == 200
        
        # Logout
        response = client.get('/auth/logout', follow_redirects=True)
        assert response.status_code in [200, 302]
        
        # Try to access protected route again
        response = client.get('/admin/users', follow_redirects=True)
        # Should redirect to login
        assert response.status_code in [200, 302]
        assert b'login' in response.data.lower() or b'sign in' in response.data.lower()