import pytest
from flask import url_for
from models import User, Role, Session
import tempfile
import os


class TestAdminMaliciousUploadsRoutes:
    """Test cases for admin malicious uploads routes."""

    def test_malicious_uploads_requires_admin_role(self, client):
        """Test that malicious uploads route requires admin role."""
        response = client.get('/admin/malicious-uploads')
        # Should redirect to login or show unauthorized
        assert response.status_code in [302, 403]

    def test_malicious_uploads_get(self, client, auth_client):
        """Test getting the malicious uploads page."""
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
        
        response = client.get('/admin/malicious-uploads')
        assert response.status_code == 200
        assert b'Malicious Uploads' in response.data

    def test_malicious_uploads_with_log_file(self, client, auth_client, app):
        """Test malicious uploads page with log file content."""
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
        
        # Create a temporary log file with test data
        log_content = """[2023-01-01 12:00:00] zip=test.zip user=testuser ip=127.0.0.1 reason=invalid_path entry=../malicious.exe
[2023-01-01 12:05:00] zip=another.zip user=otheruser ip=192.168.1.1 reason=large_file entry=file.dat"""
        
        # Write to the expected log file location
        log_dir = app.config.get('BASE_DIR', '.') + '/logs'
        os.makedirs(log_dir, exist_ok=True)
        log_file_path = log_dir + '/malicious_uploads.log'
        
        with open(log_file_path, 'w') as f:
            f.write(log_content)
        
        try:
            response = client.get('/admin/malicious-uploads')
            assert response.status_code == 200
            assert b'Malicious Uploads' in response.data
            assert b'test.zip' in response.data
            assert b'another.zip' in response.data
        finally:
            # Clean up the temporary log file
            if os.path.exists(log_file_path):
                os.remove(log_file_path)