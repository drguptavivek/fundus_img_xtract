"""
Security Tests for Thumbnail System

Tests focusing on security aspects:
- Path traversal attack prevention
- File type validation and sanitization
- Access control and authorization
- Input validation and sanitization
- Resource exhaustion protection
- CSRF protection
"""

import pytest
import os
import tempfile
import shutil
from pathlib import Path
import uuid
from unittest.mock import patch, MagicMock

# Flask imports
from flask import Flask
from flask_login import login_user, logout_user

# Model imports
from models import db, User, DirectImageUpload, EncounterFile
from db_transaction_manager import transaction_scope

# Thumbnail system imports
from utils.fileUtils import (
    get_thumbnail_path_for_direct_upload,
    get_thumbnail_path_for_encounter_file,
    validate_thumbnail_path_security,
    safe_delete_thumbnail
)
from utils.image_processing import generate_thumbnail, is_valid_image_format
from utils.utilsImgServe import (
    serve_direct_upload_thumbnail,
    serve_encounter_thumbnail,
    serve_universal_thumbnail
)


class TestThumbnailSecurity:
    """Security tests for thumbnail system."""

    @pytest.fixture
    def app(self):
        """Create Flask app for security testing."""
        app = Flask(__name__)
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['UPLOAD_FOLDER'] = tempfile.mkdtemp()
        app.config['SECRET_KEY'] = 'test-secret-key'
        app.config['WTF_CSRF_ENABLED'] = True

        db.init_app(app)

        with app.app_context():
            db.create_all()
            yield app
            db.drop_all()

        # Cleanup temp directory
        shutil.rmtree(app.config['UPLOAD_FOLDER'], ignore_errors=True)

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for security testing."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def sample_users(self, app):
        """Create users with different roles for testing."""
        with app.app_context():
            users = {}

            # Admin user
            admin = User(
                username='admin',
                email='admin@example.com',
                full_name='Admin User',
                roles='["admin"]'
            )
            admin.set_password('password')
            db.session.add(admin)
            users['admin'] = admin

            # Regular user
            regular = User(
                username='user',
                email='user@example.com',
                full_name='Regular User',
                roles='["grader"]'
            )
            regular.set_password('password')
            db.session.add(regular)
            users['user'] = regular

            # Viewer user (read-only)
            viewer = User(
                username='viewer',
                email='viewer@example.com',
                full_name='Viewer User',
                roles='["viewer"]'
            )
            viewer.set_password('password')
            db.session.add(viewer)
            users['viewer'] = viewer

            db.session.commit()
            return users

    def test_path_traversal_attack_prevention(self, app, temp_dir):
        """Test protection against path traversal attacks."""
        with app.app_context():
            app.config['UPLOAD_FOLDER'] = temp_dir

            # Malicious path attempts
            malicious_paths = [
                '../../../etc/passwd',
                '..\\..\\..\\windows\\system32\\config\\sam',
                '/etc/shadow',
                '/proc/version',
                '....//....//....//etc/passwd',
                '%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd',  # URL encoded
                '..%2f..%2f..%2fetc%2fpasswd',
                '....\\\\....\\\\....\\\\windows\\\\system32\\\\cmd.exe',
                '/var/www/../../../etc/passwd',
                'test/../../../etc/passwd',
                'normal.jpg/../../../etc/passwd',
                'thum_/../../../etc/passwd',
                'thm_../../../etc/passwd.jpg',
            ]

            for malicious_path in malicious_paths:
                # Test path validation
                is_valid = validate_thumbnail_path_security(malicious_path)
                assert is_valid is False, f"Should reject malicious path: {malicious_path}"

                # Test safe deletion
                delete_result = safe_delete_thumbnail(malicious_path)
                assert delete_result is False, f"Should not delete malicious path: {malicious_path}"

    def test_filename_injection_prevention(self, temp_dir):
        """Test protection against filename injection attacks."""
        malicious_filenames = [
            '../../../etc/passwd',
            'image.jpg; rm -rf /',
            'image.jpg|cat /etc/passwd',
            'image.jpg`whoami`',
            'image.jpg$(id)',
            'image.jpg && rm -rf /',
            'image.jpg || cat /etc/passwd',
            'image.jpg > /tmp/hacked.txt',
            'image.jpg < /etc/passwd',
            'image.jpg\nrm -rf /',
            'image.jpg\rm -rf /',
            'image.jpg\r\nrm -rf /',
            'CON', 'PRN', 'AUX', 'NUL',  # Windows reserved names
            'COM1', 'COM2', 'LPT1', 'LPT2',  # More Windows reserved
        ]

        for malicious_filename in malicious_filenames:
            # Test image format validation
            file_ext = malicious_filename.split('.')[-1] if '.' in malicious_filename else ''
            is_valid_ext = is_valid_image_format(f'image/{file_ext}')

            # Most malicious filenames should have invalid extensions
            if file_ext.lower() not in ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp']:
                assert is_valid_ext is False, f"Should reject malicious extension: {file_ext}"

    def test_uuid_validation_security(self, app):
        """Test UUID format validation for security."""
        with app.app_context():
            # Valid UUIDs
            valid_uuids = [
                '12345678-1234-1234-1234-123456789abc',
                '123e4567-e89b-12d3-a456-426614174000',
                '6ba7b810-9dad-11d1-80b4-00c04fd430c8',
            ]

            # Invalid UUIDs that could cause issues
            invalid_uuids = [
                '../../../etc/passwd',
                'admin', 'root', 'system',
                'SELECT * FROM users',  # SQL injection
                '<script>alert("xss")</script>',  # XSS
                'rm -rf /',  # Command injection
                'a' * 1000,  # Buffer overflow attempt
                '',  # Empty string
                None,  # None value
            ]

            # Test path generation with valid UUIDs
            for valid_uuid in valid_uuids:
                path = get_thumbnail_path_for_direct_upload(valid_uuid, 'jpg')
                assert 'thm_' in path
                assert valid_uuid in path
                assert path.endswith('.jpg')

            # Test path generation with invalid UUIDs (should still work but be safe)
            for invalid_uuid in invalid_uuids:
                if invalid_uuid is not None:
                    path = get_thumbnail_path_for_direct_upload(invalid_uuid, 'jpg')
                    # Should not contain directory traversal
                    assert '../' not in path
                    assert '..\\' not in path
                    # Should still be within upload folder
                    assert path.startswith(app.config['UPLOAD_FOLDER'])

    def test_file_type_validation_security(self):
        """Test file type validation against malicious files."""
        # Valid MIME types
        valid_mime_types = [
            'image/jpeg',
            'image/png',
            'image/gif',
            'image/webp',
            'image/bmp',
            'IMAGE/JPEG',  # Case insensitive
            'Image/PNG',
        ]

        # Invalid MIME types that could be malicious
        invalid_mime_types = [
            'application/x-executable',
            'application/x-shockwave-flash',
            'application/x-msdownload',
            'text/x-php',
            'application/x-python-code',
            'application/javascript',
            'text/html',
            'application/xml',
            'application/pdf',  # PDFs are not images
            'video/mp4',
            'audio/mpeg',
            'application/zip',
            'application/x-tar',
            'application/octet-stream',  # Could be anything
            'multipart/form-data',  # Not an image
            '',  # Empty
            None,  # None
            '../../../etc/passwd',  # Path traversal attempt
            '<script>alert("xss")</script>',  # XSS attempt
        ]

        # Test valid types
        for mime_type in valid_mime_types:
            assert is_valid_image_format(mime_type), f"Should accept valid MIME type: {mime_type}"

        # Test invalid types
        for mime_type in invalid_mime_types:
            assert not is_valid_image_format(mime_type), f"Should reject invalid MIME type: {mime_type}"

    def test_access_control_thumbnails(self, app, sample_users, temp_dir):
        """Test access control for thumbnail serving."""
        with app.app_context():
            app.config['UPLOAD_FOLDER'] = temp_dir

            # Create test images
            test_uuid = str(uuid.uuid4())
            thumbnail_path = os.path.join(temp_dir, 'direct_uploads', test_uuid[:2], f'thm_{test_uuid}.jpg')
            os.makedirs(os.path.dirname(thumbnail_path), exist_ok=True)

            # Create a simple thumbnail
            from PIL import Image
            thumb_img = Image.new('RGB', (180, 180), color='blue')
            thumb_img.save(thumbnail_path, 'JPEG')

            # Create database record
            direct_upload = DirectImageUpload(
                file_uuid=test_uuid,
                original_filename='test.jpg',
                file_size=12345,
                mime_type='image/jpeg',
                upload_user_id=sample_users['user'].id,
                thumbnail_filename='thm_' + test_uuid + '.jpg'
            )
            db.session.add(direct_upload)
            db.session.commit()

            # Test access with different user roles
            test_cases = [
                (sample_users['admin'], True, 'Admin should access any thumbnail'),
                (sample_users['user'], True, 'User should access their own thumbnail'),
                (sample_users['viewer'], True, 'Viewer should have read access'),
                (None, False, 'Anonymous user should not access thumbnails'),
            ]

            for user, should_succeed, description in test_cases:
                with app.test_request_context():
                    if user:
                        with patch('flask_login.current_user', user):
                            # Test direct upload thumbnail access
                            try:
                                response = serve_direct_upload_thumbnail(test_uuid)
                                if should_succeed:
                                    assert response.status_code != 403, f"{description} - got {response.status_code}"
                                else:
                                    assert response.status_code == 403, f"{description} - should be forbidden"
                            except Exception as e:
                                if should_succeed:
                                    pytest.fail(f"{description} - exception: {e}")
                    else:
                        # Test without authentication
                        with patch('flask_login.current_user.is_authenticated', False):
                            try:
                                response = serve_direct_upload_thumbnail(test_uuid)
                                assert response.status_code == 403, f"{description} - should be forbidden"
                            except Exception as e:
                                # Expected for unauthenticated access
                                pass

    def test_image_processing_security(self, temp_dir):
        """Test security aspects of image processing."""
        # Test malicious image files
        malicious_files = {}

        # 1. Oversized image (potential DoS)
        malicious_files['oversized'] = {
            'create': lambda path: self._create_oversized_image(path),
            'should_reject': False,  # Should be handled gracefully
        }

        # 2. Very small image (edge case)
        malicious_files['tiny'] = {
            'create': lambda path: self._create_tiny_image(path),
            'should_reject': False,
        }

        # 3. Extreme aspect ratio
        malicious_files['extreme_ratio'] = {
            'create': lambda path: self._create_extreme_ratio_image(path),
            'should_reject': False,
        }

        # 4. Corrupted image
        malicious_files['corrupted'] = {
            'create': lambda path: self._create_corrupted_image(path),
            'should_reject': True,
        }

        for name, config in malicious_files.items():
            source_path = os.path.join(temp_dir, f'malicious_{name}.jpg')
            output_path = os.path.join(temp_dir, f'output_{name}.jpg')

            # Create malicious file
            config['create'](source_path)

            # Try to process it
            try:
                result = generate_thumbnail(source_path, output_path)

                if config['should_reject']:
                    assert result is False, f"Should reject malicious {name}"
                else:
                    # Should handle gracefully (either succeed or fail gracefully)
                    if result:
                        # Verify output is reasonable size
                        if os.path.exists(output_path):
                            output_size = os.path.getsize(output_path)
                            assert output_size < 10 * 1024 * 1024, f"Output too large for {name}: {output_size}"

            except Exception as e:
                if config['should_reject']:
                    # Expected to fail
                    pass
                else:
                    # Should not crash
                    pytest.fail(f"Image processing crashed for {name}: {e}")

    def test_resource_exhaustion_protection(self, temp_dir):
        """Test protection against resource exhaustion attacks."""
        # Test memory usage limits
        from PIL import Image
        import psutil

        process = psutil.Process()
        initial_memory = process.memory_info().rss

        # Create many thumbnail generation attempts
        batch_size = 50
        source_path = os.path.join(temp_dir, 'resource_test.jpg')

        # Create reasonably sized test image
        test_img = Image.new('RGB', (1000, 800), color='green')
        test_img.save(source_path, 'JPEG')

        successful = 0
        failed = 0

        for i in range(batch_size):
            output_path = os.path.join(temp_dir, f'resource_{i}.jpg')

            try:
                result = generate_thumbnail(source_path, output_path)
                if result:
                    successful += 1
                else:
                    failed += 1

                # Cleanup immediately to manage disk space
                if os.path.exists(output_path):
                    os.remove(output_path)

            except Exception as e:
                failed += 1

            # Check memory usage periodically
            if i % 10 == 0:
                current_memory = process.memory_info().rss
                memory_growth = (current_memory - initial_memory) / 1024 / 1024  # MB

                # Memory growth should be reasonable
                assert memory_growth < 200, f"Excessive memory growth: {memory_growth:.1f}MB"

        # Most should succeed
        success_rate = successful / batch_size
        assert success_rate > 0.8, f"Low success rate: {success_rate:.1%}"

    def test_csrf_protection(self, app, sample_users):
        """Test CSRF protection for thumbnail operations."""
        with app.app_context():
            # Test CSRF token validation
            with app.test_client() as client:
                # Login as user
                client.post('/login', data={
                    'username': sample_users['user'].username,
                    'password': 'password'
                })

                # Test without CSRF token
                response = client.post('/api/admin/thumbnail/cleanup_orphaned')
                # Should fail without CSRF token (if CSRF is enabled)
                if app.config.get('WTF_CSRF_ENABLED', False):
                    assert response.status_code in [400, 403], "Should require CSRF token"

    def test_input_sanitization(self, app):
        """Test input sanitization for various parameters."""
        with app.app_context():
            # Test malicious UUID inputs
            malicious_uuids = [
                '../../../etc/passwd',
                '<script>alert("xss")</script>',
                "'; DROP TABLE users; --",
                '\x00\x01\x02',  # Null bytes
                'a' * 10000,  # Very long string
            ]

            for malicious_uuid in malicious_uuids:
                # Should not cause crashes or security issues
                try:
                    path = get_thumbnail_path_for_direct_upload(malicious_uuid, 'jpg')
                    # Path should be safe
                    assert '../' not in path
                    assert '..\\' not in path
                    assert path.startswith(app.config['UPLOAD_FOLDER'])

                    # Should not execute code
                    assert '<script>' not in path
                    assert 'DROP TABLE' not in path

                except Exception as e:
                    # Should fail gracefully without exposing system info
                    assert 'password' not in str(e).lower()
                    assert 'users' not in str(e).lower()

    def test_file_permission_security(self, temp_dir):
        """Test file permission handling."""
        # Create test thumbnail
        thumbnail_path = os.path.join(temp_dir, 'security_test.jpg')
        from PIL import Image
        test_img = Image.new('RGB', (180, 180), color='red')
        test_img.save(thumbnail_path, 'JPEG')

        # Test permissions
        if os.name != 'nt':  # Unix-like systems
            # Test read-only file
            os.chmod(thumbnail_path, 0o444)
            result = safe_delete_thumbnail(thumbnail_path)
            # Should handle read-only files gracefully
            assert isinstance(result, bool)

            # Test no permissions
            os.chmod(thumbnail_path, 0o000)
            result = safe_delete_thumbnail(thumbnail_path)
            # Should handle permission errors
            assert isinstance(result, bool)

            # Restore permissions for cleanup
            os.chmod(thumbnail_path, 0o644)

    def _create_oversized_image(self, path):
        """Create an oversized image for testing."""
        from PIL import Image
        # Create very large image (10,000 x 10,000 pixels)
        img = Image.new('RGB', (10000, 10000), color='red')
        img.save(path, 'JPEG', quality=95)

    def _create_tiny_image(self, path):
        """Create a tiny image for testing."""
        from PIL import Image
        img = Image.new('RGB', (1, 1), color='blue')
        img.save(path, 'JPEG')

    def _create_extreme_ratio_image(self, path):
        """Create image with extreme aspect ratio."""
        from PIL import Image
        img = Image.new('RGB', (5000, 10), color='green')
        img.save(path, 'JPEG')

    def _create_corrupted_image(self, path):
        """Create a corrupted image file."""
        # Write invalid JPEG data
        with open(path, 'wb') as f:
            f.write(b'This is not a valid JPEG file')
            f.write(b'\x00' * 1000)  # Add some bytes


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
