"""Test verification workflows."""

import pytest
from flask import url_for
from models import User, Role, Session
from auth.security import hash_password


class TestVerificationWorkflows:
    """Test cases for verification workflows."""

    def test_dr_verification_requires_authentication(self, client):
        """Test that DR verification requires authentication."""
        response = client.get('/verify-remedio-dr/list')
        # Should redirect to login
        assert response.status_code == 302
        assert '/login' in response.location

    def test_dr_verification_requires_proper_role(self, client, auth_client):
        """Test that DR verification requires proper role."""
        # Create a user without proper role
        with Session() as db:
            user_role = Role(name='contributor')
            db.add(user_role)
            db.flush()
            
            test_user = User(
                username='testuser_dr_verify',
                password_hash=hash_password('testpassword'),
                is_active=True
            )
            test_user.roles.append(user_role)
            db.add(test_user)
            db.commit()

        # Login as regular user
        auth_client.login('testuser_dr_verify', 'testpassword')
        
        # Try to access DR verification page
        response = client.get('/verify-remedio-dr/list')
        # Should be forbidden
        assert response.status_code in [403, 302]

    def test_dr_verification_page_loads(self, client, auth_client):
        """Test that DR verification page loads for authorized users."""
        # Create a user with optometrist role
        with Session() as db:
            optometrist_role = Role(name='optometrist')
            db.add(optometrist_role)
            db.flush()
            
            test_user = User(
                username='optometrist_dr_verify',
                password_hash=hash_password('testpassword'),
                is_active=True
            )
            test_user.roles.append(optometrist_role)
            db.add(test_user)
            db.commit()

        # Login as optometrist
        auth_client.login('optometrist_dr_verify', 'testpassword')
        
        # Access DR verification page
        response = client.get('/verify-remedio-dr/list')
        # May return 404 if no data, but should not be forbidden
        assert response.status_code in [200, 404]

    def test_glaucoma_verification_requires_authentication(self, client):
        """Test that glaucoma verification requires authentication."""
        response = client.get('/glaucoma')
        # Should redirect to login
        assert response.status_code == 302
        assert '/login' in response.location

    def test_glaucoma_verification_requires_proper_role(self, client, auth_client):
        """Test that glaucoma verification requires proper role."""
        # Create a user without proper role
        with Session() as db:
            user_role = Role(name='contributor')
            db.add(user_role)
            db.flush()
            
            test_user = User(
                username='testuser_glaucoma_verify',
                password_hash=hash_password('testpassword'),
                is_active=True
            )
            test_user.roles.append(user_role)
            db.add(test_user)
            db.commit()

        # Login as regular user
        auth_client.login('testuser_glaucoma_verify', 'testpassword')
        
        # Try to access glaucoma verification page
        response = client.get('/glaucoma')
        # Should be forbidden
        assert response.status_code in [403, 302]

    def test_glaucoma_verification_page_loads(self, client, auth_client):
        """Test that glaucoma verification page loads for authorized users."""
        # Create a user with optometrist role
        with Session() as db:
            optometrist_role = Role(name='optometrist')
            db.add(optometrist_role)
            db.flush()
            
            test_user = User(
                username='optometrist_glaucoma_verify',
                password_hash=hash_password('testpassword'),
                is_active=True
            )
            test_user.roles.append(optometrist_role)
            db.add(test_user)
            db.commit()

        # Login as optometrist
        auth_client.login('optometrist_glaucoma_verify', 'testpassword')
        
        # Access glaucoma verification page
        response = client.get('/glaucoma')
        # May return 404 if no data, but should not be forbidden
        assert response.status_code in [200, 404]