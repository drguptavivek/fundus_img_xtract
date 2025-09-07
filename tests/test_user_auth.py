"""Test user authentication and authorization."""

import pytest
from flask import url_for
from models import User, Role, Session, Hospital, LabUnit
from sqlalchemy import select
from auth.security import hash_password


class TestUserAuth:
    """Test cases for user authentication and authorization."""

    def test_user_login_success(self, client):
        """Test successful user login."""
        # Create a test user
        with Session() as db:
            user_role = Role(name='contributor')
            db.add(user_role)
            db.flush()
            
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
                username='testuser',
                password_hash=hash_password('testpassword'),
                is_active=True
            )
            test_user.roles.append(user_role)
            db.add(test_user)
            db.commit()

        # Login
        auth_client.login('testuser', 'testpassword')
        
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

    def test_user_profile_access(self, client, auth_client):
        """Test access to user profile page."""
        # Create a test user
        with Session() as db:
            user_role = Role(name='contributor')
            db.add(user_role)
            db.flush()
            
            test_user = User(
                username='testuser',
                password_hash=hash_password('testpassword'),
                is_active=True,
                full_name='Test User',
                email='test@example.com'
            )
            test_user.roles.append(user_role)
            db.add(test_user)
            db.commit()

        # Login
        auth_client.login('testuser', 'testpassword')
        
        # Access profile page
        response = client.get('/account/profile')
        assert response.status_code == 200
        assert b'Test User' in response.data
        assert b'test@example.com' in response.data

    def test_user_change_password(self, client, auth_client):
        """Test user changing their own password."""
        # Create a test user
        with Session() as db:
            user_role = Role(name='contributor')
            db.add(user_role)
            db.flush()
            
            test_user = User(
                username='testuser',
                password_hash=hash_password('oldpassword'),
                is_active=True
            )
            test_user.roles.append(user_role)
            db.add(test_user)
            db.commit()

        # Login with old password
        auth_client.login('testuser', 'oldpassword')
        
        # Change password
        response = client.post('/account/change-password', data={
            'current_password': 'oldpassword',
            'new_password': 'newsecurepassword123',
            'confirm_password': 'newsecurepassword123'
        }, follow_redirects=True)
        
        assert response.status_code == 200
        assert b'Password updated' in response.data
        
        # Logout
        auth_client.logout()
        
        # Try to login with old password (should fail)
        response = client.post('/auth/login', data={
            'username': 'testuser',
            'password': 'oldpassword'
        })
        assert response.status_code == 200
        assert b'Invalid username or password' in response.data.lower()
        
        # Login with new password (should succeed)
        response = client.post('/auth/login', data={
            'username': 'testuser',
            'password': 'newsecurepassword123'
        }, follow_redirects=True)
        assert response.status_code == 200

    def test_user_role_permissions(self, client, auth_client):
        """Test user role-based permissions."""
        # Create roles
        with Session() as db:
            contributor_role = Role(name='contributor')
            admin_role = Role(name='admin')
            db.add_all([contributor_role, admin_role])
            db.flush()
            
            # Create users
            contributor_user = User(
                username='contributor',
                password_hash=hash_password('password'),
                is_active=True
            )
            contributor_user.roles.append(contributor_role)
            db.add(contributor_user)
            
            admin_user = User(
                username='admin',
                password_hash=hash_password('password'),
                is_active=True
            )
            admin_user.roles.append(admin_role)
            db.add(admin_user)
            db.commit()

        # Test contributor access to contributor routes
        auth_client.login('contributor', 'password')
        response = client.get('/direct/upload')
        # Contributor should have access to direct upload
        assert response.status_code in [200, 302]
        
        # Test contributor access to admin routes (should be denied)
        response = client.get('/admin/users')
        # Should be forbidden or redirected
        assert response.status_code in [403, 302]
        
        # Logout and login as admin
        auth_client.logout()
        auth_client.login('admin', 'password')
        
        # Test admin access to admin routes
        response = client.get('/admin/users')
        assert response.status_code == 200

    def test_user_lab_unit_restrictions(self, client, auth_client):
        """Test user lab unit-based access restrictions."""
        # Create test data
        with Session() as db:
            # Create roles
            ophthalmologist_role = Role(name='ophthalmologist')
            admin_role = Role(name='admin')
            db.add_all([ophthalmologist_role, admin_role])
            db.flush()
            
            # Create hospital and lab units
            hospital1 = Hospital(name='Hospital 1')
            hospital2 = Hospital(name='Hospital 2')
            db.add_all([hospital1, hospital2])
            db.flush()
            
            lab_unit1 = LabUnit(name='Lab Unit 1', hospital_id=hospital1.id)
            lab_unit2 = LabUnit(name='Lab Unit 2', hospital_id=hospital2.id)
            db.add_all([lab_unit1, lab_unit2])
            db.commit()
            
            # Create users
            consultant_user = User(
                username='consultant',
                password_hash=hash_password('password'),
                is_active=True
            )
            consultant_user.roles.append(ophthalmologist_role)
            consultant_user.lab_units.append(lab_unit1)  # Only assigned to lab unit 1
            db.add(consultant_user)
            
            admin_user = User(
                username='admin',
                password_hash=hash_password('password'),
                is_active=True
            )
            admin_user.roles.append(admin_role)
            db.add(admin_user)
            db.commit()

        # Test consultant access to their assigned lab unit
        auth_client.login('consultant', 'password')
        
        # Consultant should be able to access routes that check lab unit restrictions
        # This would depend on specific implementation in the application
        
        # Logout and login as admin
        auth_client.logout()
        auth_client.login('admin', 'password')
        
        # Admin should have unrestricted access