import pytest
from flask import url_for
from models import User, Role, Session
from sqlalchemy import select
from auth.security import hash_password


class TestAdminChangePasswordRoutes:
    """Test cases for admin change password routes."""

    def test_change_password_requires_admin_role(self, client, auth_client):
        """Test that change password requires admin role."""
        response = client.get('/admin/change-password')
        # Should redirect to login or show unauthorized
        assert response.status_code in [302, 403]

    def test_change_password_get(self, client, auth_client):
        """Test getting the change password page."""
        # Create admin user and login
        with Session() as db:
            admin_role = Role(name='admin')
            db.add(admin_role)
            db.flush()
            
            admin_user = User(
                username='admin',
                password_hash='hashed_password',
                is_active=True
            )
            admin_user.roles.append(admin_role)
            db.add(admin_user)
            db.commit()

        auth_client.login('admin', 'password')
        
        response = client.get('/admin/change-password')
        assert response.status_code == 200
        assert b'Change Password' in response.data

    def test_change_password_post_success(self, client, auth_client):
        """Test successfully changing a user's password."""
        # Create admin user and test user
        with Session() as db:
            admin_role = Role(name='admin')
            db.add(admin_role)
            db.flush()
            
            admin_user = User(
                username='admin',
                password_hash='hashed_password',
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

        auth_client.login('admin', 'password')
        
        # Change user's password
        response = client.post('/admin/change-password', data={
            'username': 'testuser',
            'new_password': 'newsecurepassword123',
            'confirm_password': 'newsecurepassword123'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        assert b'Password updated' in response.data

    def test_change_password_post_user_not_found(self, client, auth_client):
        """Test changing password for non-existent user."""
        # Create admin user and login
        with Session() as db:
            admin_role = Role(name='admin')
            db.add(admin_role)
            db.flush()
            
            admin_user = User(
                username='admin',
                password_hash='hashed_password',
                is_active=True
            )
            admin_user.roles.append(admin_role)
            db.add(admin_user)
            db.commit()

        auth_client.login('admin', 'password')
        
        # Try to change password for non-existent user
        response = client.post('/admin/change-password', data={
            'username': 'nonexistentuser',
            'new_password': 'newsecurepassword123',
            'confirm_password': 'newsecurepassword123'
        })
        
        assert response.status_code == 200
        assert b'User not found' in response.data

    def test_change_password_post_password_mismatch(self, client, auth_client):
        """Test changing password with mismatched passwords."""
        # Create admin user and test user
        with Session() as db:
            admin_role = Role(name='admin')
            db.add(admin_role)
            db.flush()
            
            admin_user = User(
                username='admin',
                password_hash='hashed_password',
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

        auth_client.login('admin', 'password')
        
        # Try to change password with mismatch
        response = client.post('/admin/change-password', data={
            'username': 'testuser',
            'new_password': 'newsecurepassword123',
            'confirm_password': 'differentpassword'
        })
        
        assert response.status_code == 200
        assert b'Passwords do not match' in response.data

    def test_change_password_post_short_password(self, client, auth_client):
        """Test changing password with too short password."""
        # Create admin user and test user
        with Session() as db:
            admin_role = Role(name='admin')
            db.add(admin_role)
            db.flush()
            
            admin_user = User(
                username='admin',
                password_hash='hashed_password',
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

        auth_client.login('admin', 'password')
        
        # Try to change password with short password
        response = client.post('/admin/change-password', data={
            'username': 'testuser',
            'new_password': 'short',
            'confirm_password': 'short'
        })
        
        assert response.status_code == 200
        assert b'at least 10 characters' in response.data.lower()