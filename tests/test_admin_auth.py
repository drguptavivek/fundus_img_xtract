"""Test admin and auth functionality."""

import pytest
from flask import url_for
from models import User, Role, Session
from sqlalchemy import select
from auth.security import hash_password


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
                username='regularuser',
                password_hash=hash_password('regularpassword'),
                is_active=True
            )
            regular_user.roles.append(user_role)
            db.add(regular_user)
            db.commit()

        # Login as regular user
        response = auth_client.login('regularuser', 'regularpassword')
        
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
                username='admin',
                password_hash=hash_password('adminpassword'),
                is_active=True,
                full_name='Administrator'
            )
            admin_user.roles.append(admin_role)
            db.add(admin_user)
            db.commit()

        # Login as admin
        response = auth_client.login('admin', 'adminpassword')
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
                username='admin',
                password_hash=hash_password('adminpassword'),
                is_active=True
            )
            admin_user.roles.append(admin_role)
            db.add(admin_user)
            db.commit()

        # Login
        auth_client.login('admin', 'adminpassword')
        
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

    def test_admin_change_password_get(self, client, auth_client):
        """Test getting the change password page."""
        # Create admin user
        with Session() as db:
            admin_role = Role(name='admin')
            db.add(admin_role)
            db.flush()
            
            admin_user = User(
                username='admin',
                password_hash=hash_password('adminpassword'),
                is_active=True
            )
            admin_user.roles.append(admin_role)
            db.add(admin_user)
            db.commit()

        # Login as admin
        auth_client.login('admin', 'adminpassword')
        
        response = client.get('/admin/change-password')
        assert response.status_code == 200
        assert b'Change Password' in response.data

    def test_admin_change_password_post_success(self, client, auth_client):
        """Test successfully changing password."""
        # Create admin user and test user
        with Session() as db:
            admin_role = Role(name='admin')
            db.add(admin_role)
            db.flush()
            
            admin_user = User(
                username='admin',
                password_hash=hash_password('adminpassword'),
                is_active=True
            )
            admin_user.roles.append(admin_role)
            db.add(admin_user)
            
            test_user = User(
                username='testuser',
                password_hash=hash_password('oldpassword'),
                is_active=True
            )
            db.add(test_user)
            db.commit()

        # Login as admin
        auth_client.login('admin', 'adminpassword')
        
        # Change password
        response = client.post('/admin/change-password', data={
            'username': 'testuser',
            'new_password': 'newsecurepassword123',
            'confirm_password': 'newsecurepassword123'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        assert b'Password updated' in response.data

    def test_admin_change_password_post_mismatch(self, client, auth_client):
        """Test changing password with mismatched passwords."""
        # Create admin user and test user
        with Session() as db:
            admin_role = Role(name='admin')
            db.add(admin_role)
            db.flush()
            
            admin_user = User(
                username='admin',
                password_hash=hash_password('adminpassword'),
                is_active=True
            )
            admin_user.roles.append(admin_role)
            db.add(admin_user)
            
            test_user = User(
                username='testuser',
                password_hash=hash_password('oldpassword'),
                is_active=True
            )
            db.add(test_user)
            db.commit()

        # Login as admin
        auth_client.login('admin', 'adminpassword')
        
        # Try to change password with mismatch
        response = client.post('/admin/change-password', data={
            'username': 'testuser',
            'new_password': 'newpassword123',
            'confirm_password': 'differentpassword'
        })
        
        assert response.status_code == 200
        assert b'Passwords do not match' in response.data

    def test_admin_manage_roles_get(self, client, auth_client):
        """Test getting the manage roles page."""
        # Create admin user
        with Session() as db:
            admin_role = Role(name='admin')
            db.add(admin_role)
            db.flush()
            
            admin_user = User(
                username='admin',
                password_hash=hash_password('adminpassword'),
                is_active=True
            )
            admin_user.roles.append(admin_role)
            db.add(admin_user)
            db.commit()

        # Login as admin
        auth_client.login('admin', 'adminpassword')
        
        response = client.get('/admin/roles')
        assert response.status_code == 200
        assert b'Roles' in response.data

    def test_admin_manage_roles_post_success(self, client, auth_client):
        """Test successfully adding a new role."""
        # Create admin user
        with Session() as db:
            admin_role = Role(name='admin')
            db.add(admin_role)
            db.flush()
            
            admin_user = User(
                username='admin',
                password_hash=hash_password('adminpassword'),
                is_active=True
            )
            admin_user.roles.append(admin_role)
            db.add(admin_user)
            db.commit()

        # Login as admin
        auth_client.login('admin', 'adminpassword')
        
        # Add new role
        response = client.post('/admin/roles', data={
            'name': 'new_test_role'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        
        # Check that role was added to database
        with Session() as db:
            role = db.execute(
                select(Role).where(Role.name == 'new_test_role')
            ).scalar_one_or_none()
            assert role is not None
            assert role.name == 'new_test_role'