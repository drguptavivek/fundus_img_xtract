"""Test file uploading functionality (ZIP and direct uploads)."""

import pytest
import os
import tempfile
from flask import url_for
from models import User, Role, Session
from auth.security import hash_password


class TestFileUploading:
    """Test cases for file uploading functionality."""

    def test_upload_form_requires_auth(client):
        # Accessing the upload form without authentication should redirect to login
        response = client.get('/remedio_zip_uploads/upload_files')
        # Should redirect to login
        assert response.status_code == 302
        assert '/login' in response.location

    def test_zip_upload_requires_proper_role(self, client, auth_client):
        """Test that ZIP upload requires fileUploader or admin role."""
        # Create a user without proper role
        with Session() as db:
            user_role = Role(name='contributor')
            db.add(user_role)
            db.flush()
            
            test_user = User(
                username='testuser_zip',
                password_hash=hash_password('testpassword'),
                is_active=True
            )
            test_user.roles.append(user_role)
            db.add(test_user)
            db.commit()

        # Login as regular user
        auth_client.login('testuser_zip', 'testpassword')
        
        # Try to access upload page
        response = client.get('/remedio_zip_uploads/upload_files')
        # Should be forbidden
        assert response.status_code in [403, 302]

    def test_upload_form_accessible_to_file_uploader(self, client, file_uploader_user):
        # Log in as file uploader
        with client.session_transaction() as sess:
            sess['_user_id'] = str(file_uploader_user.id)
    
        # Accessing the upload form should work now
        response = client.get('/remedio_zip_uploads/upload_files')
        assert response.status_code == 200
        assert b'Upload' in response.data

    def test_direct_upload_requires_authentication(self, client):
        """Test that direct upload requires authentication."""
        response = client.get('/direct/upload')
        # Should redirect to login
        assert response.status_code == 302
        assert '/login' in response.location

    def test_direct_upload_requires_proper_role(self, client, auth_client):
        """Test that direct upload requires contributor, data_manager, or admin role."""
        # Create a user without proper role
        with Session() as db:
            user_role = Role(name='optometrist')
            db.add(user_role)
            db.flush()
            
            test_user = User(
                username='testuser_direct',
                password_hash=hash_password('testpassword'),
                is_active=True
            )
            test_user.roles.append(user_role)
            db.add(test_user)
            db.commit()

        # Login as regular user
        auth_client.login('testuser_direct', 'testpassword')
        
        # Try to access direct upload page
        response = client.get('/direct/upload')
        # Should be forbidden
        assert response.status_code in [403, 302]

    def test_direct_upload_page_loads(self, client, auth_client):
        """Test that direct upload page loads for authorized users."""
        # Create a user with contributor role
        with Session() as db:
            contributor_role = Role(name='contributor')
            db.add(contributor_role)
            db.flush()
            
            test_user = User(
                username='contributor_direct',
                password_hash=hash_password('testpassword'),
                is_active=True
            )
            test_user.roles.append(contributor_role)
            db.add(test_user)
            db.commit()

        # Login as contributor
        auth_client.login('contributor_direct', 'testpassword')
        
        # Access direct upload page
        response = client.get('/direct/upload')
        assert response.status_code == 200
        assert b'Upload' in response.data

    def test_zip_upload_post_no_files(self, client, auth_client):
        """Test ZIP upload with no files selected."""
        # Create a user with fileUploader role
        with Session() as db:
            uploader_role = Role(name='fileUploader')
            db.add(uploader_role)
            db.flush()
            
            test_user = User(
                username='uploader_no_files',
                password_hash=hash_password('testpassword'),
                is_active=True
            )
            test_user.roles.append(uploader_role)
            db.add(test_user)
            db.commit()

        # Login as uploader
        auth_client.login('uploader_no_files', 'testpassword')
        
        # Post with no files
        response = client.post('/upload', data={}, follow_redirects=True)
        assert response.status_code == 200
        assert b'No files uploaded' in response.data

    def test_direct_upload_post_no_files(self, client, auth_client):
        """Test direct upload with no files selected."""
        # Create a user with contributor role
        with Session() as db:
            contributor_role = Role(name='contributor')
            db.add(contributor_role)
            db.flush()
            
            test_user = User(
                username='contributor_no_files',
                password_hash=hash_password('testpassword'),
                is_active=True
            )
            test_user.roles.append(contributor_role)
            db.add(test_user)
            db.commit()

        # Login as contributor
        auth_client.login('contributor_no_files', 'testpassword')
        
        # Post with no files and missing form data
        response = client.post('/direct/upload', data={}, follow_redirects=True)
        assert response.status_code == 200
        assert b'All fields are required' in response.data