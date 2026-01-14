"""
Unit Tests for Thumbnail File Management

Tests for file path utilities, security validation, and file operations:
- Path generation and validation
- Security checks for path traversal attacks
- Thumbnail existence checking
- File operations with proper error handling
"""

import pytest
import os
import tempfile
import shutil
from pathlib import Path
import uuid

# Import the functions we're testing
from utils.fileUtils import (
    get_thumbnail_path_direct,
    get_thumbnail_path_encounter,
    validate_thumbnail_filename,
    thumbnail_exists_direct,
    cleanup_orphaned_thumbnails,
    get_thumbnail_filename
)


class TestThumbnailFileManagement:
    """Test suite for thumbnail file management functions."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test files."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def sample_uuids(self):
        """Generate sample UUIDs for testing."""
        return [
            str(uuid.uuid4()),
            str(uuid.uuid4()),
            str(uuid.uuid4()),
            '12345678-1234-1234-1234-123456789abc',  # Fixed UUID for consistent testing
        ]

    @pytest.fixture
    def upload_folders(self, temp_dir):
        """Create upload folder structure."""
        base_dir = temp_dir
        direct_dir = os.path.join(base_dir, 'uploads', 'direct_uploads')
        encounter_dir = os.path.join(base_dir, 'uploads', 'encounter_files')

        os.makedirs(direct_dir, exist_ok=True)
        os.makedirs(encounter_dir, exist_ok=True)

        return {
            'base': base_dir,
            'direct': direct_dir,
            'encounter': encounter_dir
        }

    def test_generate_thumbnail_filename(self):
        """Test thumbnail filename generation."""
        test_uuid = '12345678-1234-1234-1234-123456789abc'

        # Test different file extensions
        assert generate_thumbnail_filename(test_uuid, 'jpg') == f'thm_{test_uuid}.jpg'
        assert generate_thumbnail_filename(test_uuid, 'jpeg') == f'thm_{test_uuid}.jpeg'
        assert generate_thumbnail_filename(test_uuid, 'png') == f'thm_{test_uuid}.png'
        assert generate_thumbnail_filename(test_uuid, 'webp') == f'thm_{test_uuid}.webp'

        # Test case insensitive extensions
        assert generate_thumbnail_filename(test_uuid, 'JPG') == f'thm_{test_uuid}.JPG'
        assert generate_thumbnail_filename(test_uuid, 'PNG') == f'thm_{test_uuid}.PNG'

        # Test edge cases
        assert generate_thumbnail_filename(test_uuid, '') == f'thm_{test_uuid}.'
        assert generate_thumbnail_filename('', 'jpg') == 'thm_.jpg'

    def test_get_thumbnail_path_for_direct_upload(self, upload_folders, sample_uuids):
        """Test direct upload thumbnail path generation."""
        # Mock the upload folder configuration
        import utils.fileUtils
        original_upload_folder = getattr(utils.fileUtils, 'UPLOAD_FOLDER', None)
        utils.fileUtils.UPLOAD_FOLDER = upload_folders['base']

        try:
            test_uuid = sample_uuids[0]

            # Test basic path generation
            path = get_thumbnail_path_for_direct_upload(test_uuid, 'jpg')
            expected = os.path.join(upload_folders['direct'], f'thm_{test_uuid}.jpg')
            assert path == expected

            # Test different extensions
            path_png = get_thumbnail_path_for_direct_upload(test_uuid, 'png')
            expected_png = os.path.join(upload_folders['direct'], f'thm_{test_uuid}.png')
            assert path_png == expected_png

            # Test that the directory exists (or can be created)
            dir_path = os.path.dirname(path)
            assert os.path.exists(dir_path) or os.path.isdir(dir_path)

        finally:
            # Restore original config
            if original_upload_folder:
                utils.fileUtils.UPLOAD_FOLDER = original_upload_folder

    def test_get_thumbnail_path_for_encounter_file(self, upload_folders, sample_uuids):
        """Test encounter file thumbnail path generation."""
        # Mock the upload folder configuration
        import utils.fileUtils
        original_upload_folder = getattr(utils.fileUtils, 'UPLOAD_FOLDER', None)
        utils.fileUtils.UPLOAD_FOLDER = upload_folders['base']

        try:
            test_uuid = sample_uuids[0]

            # Test basic path generation
            path = get_thumbnail_path_for_encounter_file(test_uuid, 'jpg')
            expected = os.path.join(upload_folders['encounter'], f'thm_{test_uuid}.jpg')
            assert path == expected

            # Test different extensions
            path_webp = get_thumbnail_path_for_encounter_file(test_uuid, 'webp')
            expected_webp = os.path.join(upload_folders['encounter'], f'thm_{test_uuid}.webp')
            assert path_webp == expected_webp

        finally:
            # Restore original config
            if original_upload_folder:
                utils.fileUtils.UPLOAD_FOLDER = original_upload_folder

    def test_validate_thumbnail_path_security(self, upload_folders, sample_uuids):
        """Test path security validation."""
        # Mock the upload folder configuration
        import utils.fileUtils
        original_upload_folder = getattr(utils.fileUtils, 'UPLOAD_FOLDER', None)
        utils.fileUtils.UPLOAD_FOLDER = upload_folders['base']

        try:
            test_uuid = sample_uuids[0]

            # Valid paths should pass validation
            valid_path = get_thumbnail_path_for_direct_upload(test_uuid, 'jpg')
            assert validate_thumbnail_path_security(valid_path) is True

            valid_encounter_path = get_thumbnail_path_for_encounter_file(test_uuid, 'png')
            assert validate_thumbnail_path_security(valid_encounter_path) is True

            # Invalid paths should fail validation
            invalid_paths = [
                '../../../etc/passwd',  # Path traversal
                '/etc/shadow',  # Absolute path outside upload folder
                os.path.join(upload_folders['base'], '..', 'malicious.jpg'),  # Relative traversal
                os.path.join(upload_folders['base'], 'subfolder', '../../../etc/passwd'),  # Deep traversal
                'C:\\Windows\\System32\\cmd.exe',  # Windows path (if applicable)
                '~/.ssh/id_rsa',  # Home directory access
            ]

            for invalid_path in invalid_paths:
                assert validate_thumbnail_path_security(invalid_path) is False, f"Should reject: {invalid_path}"

            # Edge cases
            assert validate_thumbnail_path_security('') is False
            assert validate_thumbnail_path_security(None) is False
            assert validate_thumbnail_path_security('../normal.jpg') is False

        finally:
            # Restore original config
            if original_upload_folder:
                utils.fileUtils.UPLOAD_FOLDER = original_upload_folder

    def test_thumbnail_exists(self, upload_folders, sample_uuids):
        """Test thumbnail existence checking."""
        # Mock the upload folder configuration
        import utils.fileUtils
        original_upload_folder = getattr(utils.fileUtils, 'UPLOAD_FOLDER', None)
        utils.fileUtils.UPLOAD_FOLDER = upload_folders['base']

        try:
            test_uuid = sample_uuids[0]
            ext = 'jpg'

            # Test non-existent thumbnail
            path = get_thumbnail_path_for_direct_upload(test_uuid, ext)
            assert thumbnail_exists(path) is False

            # Create a file and test existence
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w') as f:
                f.write('dummy content')

            assert thumbnail_exists(path) is True

            # Test with encounter file
            encounter_path = get_thumbnail_path_for_encounter_file(test_uuid, ext)
            assert thumbnail_exists(encounter_path) is False

            os.makedirs(os.path.dirname(encounter_path), exist_ok=True)
            with open(encounter_path, 'w') as f:
                f.write('dummy content')

            assert thumbnail_exists(encounter_path) is True

            # Test invalid paths
            assert thumbnail_exists('/nonexistent/path.jpg') is False
            assert thumbnail_exists('') is False
            assert thumbnail_exists(None) is False

        finally:
            # Restore original config
            if original_upload_folder:
                utils.fileUtils.UPLOAD_FOLDER = original_upload_folder

    def test_safe_delete_thumbnail(self, upload_folders, sample_uuids):
        """Test safe thumbnail deletion."""
        # Mock the upload folder configuration
        import utils.fileUtils
        original_upload_folder = getattr(utils.fileUtils, 'UPLOAD_FOLDER', None)
        utils.fileUtils.UPLOAD_FOLDER = upload_folders['base']

        try:
            test_uuid = sample_uuids[0]
            ext = 'jpg'

            # Test deleting non-existent file
            path = get_thumbnail_path_for_direct_upload(test_uuid, ext)
            result = safe_delete_thumbnail(path)
            assert result is True  # Should succeed (idempotent operation)

            # Create file and delete it
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w') as f:
                f.write('dummy content')

            assert os.path.exists(path) is True
            result = safe_delete_thumbnail(path)
            assert result is True
            assert os.path.exists(path) is False

            # Test deleting already deleted file
            result = safe_delete_thumbnail(path)
            assert result is True  # Should still succeed

            # Test invalid paths
            assert safe_delete_thumbnail('/nonexistent/path.jpg') is True  # Should not raise error
            assert safe_delete_thumbnail('') is False  # Should reject empty path
            assert safe_delete_thumbnail(None) is False  # Should reject None

            # Test path outside upload folder (should be rejected)
            malicious_path = '/etc/passwd'
            result = safe_delete_thumbnail(malicious_path)
            assert result is False  # Should reject for security

        finally:
            # Restore original config
            if original_upload_folder:
                utils.fileUtils.UPLOAD_FOLDER = original_upload_folder

    def test_path_generation_with_various_uuids(self, upload_folders, sample_uuids):
        """Test path generation with various UUID formats."""
        # Mock the upload folder configuration
        import utils.fileUtils
        original_upload_folder = getattr(utils.fileUtils, 'UPLOAD_FOLDER', None)
        utils.fileUtils.UPLOAD_FOLDER = upload_folders['base']

        try:
            for test_uuid in sample_uuids:
                # Test direct upload paths
                direct_path = get_thumbnail_path_for_direct_upload(test_uuid, 'jpg')
                assert 'thm_' in direct_path
                assert test_uuid in direct_path
                assert direct_path.endswith('.jpg')
                assert 'direct_uploads' in direct_path

                # Test encounter file paths
                encounter_path = get_thumbnail_path_for_encounter_file(test_uuid, 'png')
                assert 'thm_' in encounter_path
                assert test_uuid in encounter_path
                assert encounter_path.endswith('.png')
                assert 'encounter_files' in encounter_path

                # Paths should be different for different types
                assert direct_path != encounter_path

        finally:
            # Restore original config
            if original_upload_folder:
                utils.fileUtils.UPLOAD_FOLDER = original_upload_folder

    def test_filename_validation_edge_cases(self):
        """Test filename validation with edge cases."""
        # Test UUIDs with different formats
        valid_uuids = [
            '12345678-1234-1234-1234-123456789abc',
            '12345678123412341234123456789abc',  # Without dashes
            '123e4567-e89b-12d3-a456-426614174000',  # Different valid UUID
        ]

        for test_uuid in valid_uuids:
            filename = generate_thumbnail_filename(test_uuid, 'jpg')
            assert filename.startswith('thm_')
            assert filename.endswith('.jpg')
            assert test_uuid in filename

        # Test invalid UUIDs (should still generate filename)
        invalid_uuids = [
            'not-a-uuid',
            '123',
            '',
            'special-chars-!@#$%^&*()',
        ]

        for invalid_uuid in invalid_uuids:
            filename = generate_thumbnail_filename(invalid_uuid, 'jpg')
            assert filename.startswith('thm_')
            assert filename.endswith('.jpg')

    def test_concurrent_path_operations(self, upload_folders, sample_uuids):
        """Test thread-safe path operations."""
        import threading
        import time

        # Mock the upload folder configuration
        import utils.fileUtils
        original_upload_folder = getattr(utils.fileUtils, 'UPLOAD_FOLDER', None)
        utils.fileUtils.UPLOAD_FOLDER = upload_folders['base']

        try:
            results = []
            errors = []

            def generate_paths(uuid_idx):
                try:
                    test_uuid = sample_uuids[uuid_idx % len(sample_uuids)]
                    for i in range(10):  # Generate multiple paths per thread
                        path = get_thumbnail_path_for_direct_upload(test_uuid, 'jpg')
                        results.append(path)
                        time.sleep(0.001)  # Small delay to increase chance of race conditions
                except Exception as e:
                    errors.append(e)

            # Create multiple threads
            threads = []
            for i in range(5):
                thread = threading.Thread(target=generate_paths, args=(i,))
                threads.append(thread)

            # Start all threads
            for thread in threads:
                thread.start()

            # Wait for completion
            for thread in threads:
                thread.join()

            # Verify no errors occurred
            assert len(errors) == 0, f"Errors occurred: {errors}"

            # Verify all paths are valid
            assert len(results) == 50  # 5 threads * 10 paths each
            for path in results:
                assert validate_thumbnail_path_security(path)

        finally:
            # Restore original config
            if original_upload_folder:
                utils.fileUtils.UPLOAD_FOLDER = original_upload_folder

    def test_permission_handling(self, upload_folders, sample_uuids, monkeypatch):
        """Test handling of file permission issues."""
        # Mock the upload folder configuration
        import utils.fileUtils
        original_upload_folder = getattr(utils.fileUtils, 'UPLOAD_FOLDER', None)
        utils.fileUtils.UPLOAD_FOLDER = upload_folders['base']

        try:
            test_uuid = sample_uuids[0]
            path = get_thumbnail_path_for_direct_upload(test_uuid, 'jpg')

            # Mock os.path.exists to simulate permission error
            def mock_exists(path):
                if 'permission' in path.lower():
                    raise PermissionError("Permission denied")
                return os.path.exists(path)

            monkeypatch.setattr(os.path, 'exists', mock_exists)

            # Should handle permission errors gracefully
            result = thumbnail_exists(path + '_permission')
            assert result is False

        finally:
            # Restore original config
            if original_upload_folder:
                utils.fileUtils.UPLOAD_FOLDER = original_upload_folder


if __name__ == '__main__':
    pytest.main([__file__, '-v'])