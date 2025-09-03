import pytest
from flask import url_for
from models import User, Role, Session
from sqlalchemy import select
from sqlalchemy import select


class TestAdminUsersRoutes:
    """Test cases for admin users routes."""

    def test_users_list_requires_admin_role(self, client, auth_client):
        """Test that users list requires admin role."""
        # Login as non-admin
        response = auth_client.login('nonadmin', 'password')
        response = client.get('/admin/users')
        # Should redirect to login or show unauthorized
        assert response.status_code in [302, 403]

    def test_users_list_get(self, client, auth_client):
        """Test getting the users list page."""
        # First create an admin user and login
        with Session() as db:
            # Check if admin role exists, create if not
            admin_role = db.execute(select(Role).where(Role.name == 'admin')).scalar_one_or_none()
            if not admin_role:
                admin_role = Role(name='admin')
                db.add(admin_role)
                db.flush()
            
            # Check if admin user exists, create if not
            admin_user = db.execute(select(User).where(User.username == 'admin')).scalar_one_or_none()
            if not admin_user:
                admin_user = User(
                    username='admin',
                    password_hash='hashed_password',
                    is_active=True
                )
                admin_user.roles.append(admin_role)
                db.add(admin_user)
                db.commit()

        # Login as admin
        auth_client.login('admin', 'password')
        
        response = client.get('/admin/users')
        assert response.status_code == 200
        assert b'Users' in response.data

    def test_add_user_get(self, client, auth_client):
        """Test getting the add user form."""
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
        
        response = client.get('/admin/users/new')
        assert response.status_code == 200
        assert b'Add User' in response.data

    def test_add_user_post_success(self, client, auth_client):
        """Test successfully adding a user."""
        # Create admin user and login
        with Session() as db:
            admin_role = Role(name='admin')
            db.add(admin_role)
            db.flush()
            
            data_manager_role = Role(name='data_manager')
            db.add(data_manager_role)
            db.commit()
            
            admin_user = User(
                username='admin',
                password_hash='hashed_password',
                is_active=True
            )
            admin_user.roles.append(admin_role)
            db.add(admin_user)
            db.commit()

        auth_client.login('admin', 'password')
        
        # Test adding a new user
        response = client.post('/admin/users/new', data={
            'username': 'newuser',
            'new_password': 'securepassword123',
            'confirm_password': 'securepassword123',
            'active': 'on',
            'roles': ['data_manager'],
            'full_name': 'New User',
            'email': 'newuser@example.com',
            'phone': '1234567890'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        
        # Check that user was added to database
        with Session() as db:
            user = db.execute(
                select(User).where(User.username == 'newuser')
            ).scalar_one_or_none()
            assert user is not None
            assert user.full_name == 'New User'
            assert len(user.roles) == 1
            assert user.roles[0].name == 'data_manager'

    def test_add_user_post_password_mismatch(self, client, auth_client):
        """Test adding a user with password mismatch."""
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
        
        # Test adding a new user with password mismatch
        response = client.post('/admin/users/new', data={
            'username': 'newuser',
            'new_password': 'securepassword123',
            'confirm_password': 'differentpassword',
            'active': 'on',
            'full_name': 'New User',
            'email': 'newuser@example.com'
        })
        
        assert response.status_code == 200
        assert b'Passwords do not match' in response.data

    def test_add_user_post_duplicate_username(self, client, auth_client):
        """Test adding a user with duplicate username."""
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
            
            # Add existing user
            existing_user = User(
                username='existinguser',
                password_hash='hashed_password',
                is_active=True
            )
            db.add(existing_user)
            db.commit()

        auth_client.login('admin', 'password')
        
        # Try to add user with same username
        response = client.post('/admin/users/new', data={
            'username': 'existinguser',
            'new_password': 'securepassword123',
            'confirm_password': 'securepassword123',
            'active': 'on',
            'full_name': 'New User',
            'email': 'newuser@example.com'
        })
        
        assert response.status_code == 200
        assert b'Username already exists' in response.data

    def test_edit_user_get(self, client, auth_client):
        """Test getting the edit user form."""
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
                password_hash='hashed_password',
                is_active=True,
                full_name='Test User',
                email='test@example.com'
            )
            db.add(test_user)
            db.commit()
            
            test_user_id = test_user.id

        auth_client.login('admin', 'password')
        
        response = client.get(f'/admin/users/{test_user_id}/edit')
        assert response.status_code == 200
        assert b'Edit User' in response.data
        assert b'Test User' in response.data

    def test_edit_user_post(self, client, auth_client):
        """Test editing a user."""
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
                password_hash='hashed_password',
                is_active=True,
                full_name='Test User',
                email='test@example.com'
            )
            db.add(test_user)
            db.commit()
            
            test_user_id = test_user.id

        auth_client.login('admin', 'password')
        
        # Edit the user
        response = client.post(f'/admin/users/{test_user_id}/edit', data={
            'full_name': 'Updated User',
            'email': 'updated@example.com',
            'phone': '0987654321'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        
        # Check that user was updated in database
        with Session() as db:
            user = db.get(User, test_user_id)
            assert user.full_name == 'Updated User'
            assert user.email == 'updated@example.com'

    def test_users_update_post(self, client, auth_client):
        """Test updating user roles and active status."""
        # Create roles and users
        with Session() as db:
            admin_role = Role(name='admin')
            data_manager_role = Role(name='data_manager')
            db.add_all([admin_role, data_manager_role])
            db.flush()
            
            # Create admin user
            admin_user = User(
                username='admin',
                password_hash='hashed_password',
                is_active=True
            )
            admin_user.roles.append(admin_role)
            db.add(admin_user)
            
            # Create test user
            test_user = User(
                username='testuser',
                password_hash='hashed_password',
                is_active=True
            )
            test_user.roles.append(data_manager_role)
            db.add(test_user)
            db.commit()
            
            test_user_id = test_user.id

        auth_client.login('admin', 'password')
        
        # Update user roles and active status
        response = client.post(f'/admin/users/{test_user_id}/update', data={
            'active': 'on',
            'roles': ['admin']  # Change role from data_manager to admin
        }, follow_redirects=True)
        
        assert response.status_code == 200
        
        # Check that user was updated in database
        with Session() as db:
            user = db.get(User, test_user_id)
            assert user.is_active == True
            assert len(user.roles) == 1
            assert user.roles[0].name == 'admin'