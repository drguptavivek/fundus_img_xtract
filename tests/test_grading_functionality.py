"""Test grading functionality."""

import pytest
from flask import url_for
from models import User, Role, Session
from auth.security import hash_password


class TestGradingFunctionality:
    """Test cases for grading functionality."""

    def test_grading_dashboard_requires_authentication(self, client):
        """Test that grading dashboard requires authentication."""
        response = client.get('/grading/')
        # Should redirect to login
        assert response.status_code == 302
        assert '/login' in response.location

    def test_grading_dashboard_requires_proper_role(self, client, auth_client):
        """Test that grading dashboard requires proper role."""
        # Create a user without proper role
        with Session() as db:
            user_role = Role(name='contributor')
            db.add(user_role)
            db.flush()
            
            test_user = User(
                username='testuser_grading',
                password_hash=hash_password('testpassword'),
                is_active=True
            )
            test_user.roles.append(user_role)
            db.add(test_user)
            db.commit()

        # Login as regular user
        auth_client.login('testuser_grading', 'testpassword')
        
        # Try to access grading dashboard
        response = client.get('/grading/')
        # Should be forbidden
        assert response.status_code in [403, 302]

    def test_grading_dashboard_loads(self, client, auth_client):
        """Test that grading dashboard loads for authorized users."""
        # Create a user with ophthalmologist role
        with Session() as db:
            ophthalmologist_role = Role(name='ophthalmologist')
            db.add(ophthalmologist_role)
            db.flush()
            
            test_user = User(
                username='ophthalmologist_grading',
                password_hash=hash_password('testpassword'),
                is_active=True
            )
            test_user.roles.append(ophthalmologist_role)
            db.add(test_user)
            db.commit()

        # Login as ophthalmologist
        auth_client.login('ophthalmologist_grading', 'testpassword')
        
        # Access grading dashboard
        response = client.get('/grading/')
        # May return 404 if no data, but should not be forbidden
        assert response.status_code in [200, 404]

    def test_dr_grading_requires_authentication(self, client):
        """Test that DR grading requires authentication."""
        response = client.get('/grading/remedio-dr')
        # Should redirect to login
        assert response.status_code == 302
        assert '/login' in response.location

    def test_dr_grading_requires_proper_role(self, client, auth_client):
        """Test that DR grading requires proper role."""
        # Create a user without proper role
        with Session() as db:
            user_role = Role(name='contributor')
            db.add(user_role)
            db.flush()
            
            test_user = User(
                username='testuser_dr_grading',
                password_hash=hash_password('testpassword'),
                is_active=True
            )
            test_user.roles.append(user_role)
            db.add(test_user)
            db.commit()

        # Login as regular user
        auth_client.login('testuser_dr_grading', 'testpassword')
        
        # Try to access DR grading page
        response = client.get('/grading/remedio-dr')
        # Should be forbidden
        assert response.status_code in [403, 302]

    def test_glaucoma_grading_requires_authentication(self, client):
        """Test that glaucoma grading requires authentication."""
        response = client.get('/grading/remedio-glaucoma')
        # Should redirect to login
        assert response.status_code == 302
        assert '/login' in response.location

    def test_glaucoma_grading_requires_proper_role(self, client, auth_client):
        """Test that glaucoma grading requires proper role."""
        # Create a user without proper role
        with Session() as db:
            user_role = Role(name='contributor')
            db.add(user_role)
            db.flush()
            
            test_user = User(
                username='testuser_glaucoma_grading',
                password_hash=hash_password('testpassword'),
                is_active=True
            )
            test_user.roles.append(user_role)
            db.add(test_user)
            db.commit()

        # Login as regular user
        auth_client.login('testuser_glaucoma_grading', 'testpassword')
        
        # Try to access glaucoma grading page
        response = client.get('/grading/remedio-glaucoma')
        # Should be forbidden
        assert response.status_code in [403, 302]

    def test_direct_image_grading_requires_authentication(self, client):
        """Test that direct image grading requires authentication."""
        response = client.get('/grading/direct-image')
        # Should redirect to login
        assert response.status_code == 302
        assert '/login' in response.location

    def test_direct_image_grading_requires_proper_role(self, client, auth_client):
        """Test that direct image grading requires proper role."""
        # Create a user without proper role
        with Session() as db:
            user_role = Role(name='contributor')
            db.add(user_role)
            db.flush()
            
            test_user = User(
                username='testuser_direct_grading',
                password_hash=hash_password('testpassword'),
                is_active=True
            )
            test_user.roles.append(user_role)
            db.add(test_user)
            db.commit()

        # Login as regular user
        auth_client.login('testuser_direct_grading', 'testpassword')
        
        # Try to access direct image grading page
        response = client.get('/grading/direct-image')
        # Should be forbidden
        assert response.status_code in [403, 302]