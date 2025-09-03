import pytest
from flask import url_for
from models import User, Role, Session
from sqlalchemy import select


class TestAdminRolesRoutes:
    """Test cases for admin roles routes."""

    def test_manage_roles_requires_admin_role(self, client, auth_client):
        """Test that manage roles requires admin role."""
        response = client.get('/admin/roles')
        # Should redirect to login or show unauthorized
        assert response.status_code in [302, 403]

    def test_manage_roles_get(self, client, auth_client):
        """Test getting the roles management page."""
        # Create admin user and login
        with Session() as db:
            # Check if admin role exists, create if not
            admin_role = db.execute(select(Role).where(Role.name == 'admin')).scalar_one_or_none()
            if not admin_role:
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
        
        response = client.get('/admin/roles')
        assert response.status_code == 200
        assert b'Roles' in response.data

    def test_manage_roles_post_success(self, client, auth_client):
        """Test successfully adding a new role."""
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
        
        # Add a new role
        response = client.post('/admin/roles', data={
            'name': 'new_role'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        
        # Check that role was added to database
        with Session() as db:
            role = db.execute(
                select(Role).where(Role.name == 'new_role')
            ).scalar_one_or_none()
            assert role is not None
            assert role.name == 'new_role'

    def test_manage_roles_post_duplicate_role(self, client, auth_client):
        """Test adding a duplicate role."""
        # Create admin user and existing role
        with Session() as db:
            admin_role = Role(name='admin')
            existing_role = Role(name='existing_role')
            db.add_all([admin_role, existing_role])
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
        
        # Try to add duplicate role
        response = client.post('/admin/roles', data={
            'name': 'existing_role'
        })
        
        assert response.status_code == 200
        assert b'already exists' in response.data

    def test_manage_roles_post_invalid_name(self, client, auth_client):
        """Test adding a role with invalid name."""
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
        
        # Try to add role with invalid name
        response = client.post('/admin/roles', data={
            'name': '123invalid'  # Starts with a number
        })
        
        assert response.status_code == 200
        assert b'must be' in response.data.lower()