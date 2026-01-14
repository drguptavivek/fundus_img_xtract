"""
Unit Tests for Thumbnail File Management (Simplified)

Tests for file path utilities, security validation, and file operations using the actual available functions.
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
    get_thumbnail_filename
)
from models import IMAGE_DIR


class TestThumbnailFileManagementSimple:
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

    def test_generate_thumbnail_filename(self):
        """Test thumbnail filename generation."""
        test_uuid = '12345678-1234-1234-1234-123456789abc'

        # Test basic filename generation
        filename = get_thumbnail_filename(test_uuid, 'jpg')
        expected = f'thm_{test_uuid}.jpg'
        assert filename == expected

        # Test different extensions
        assert get_thumbnail_filename(test_uuid, 'png') == f'thm_{test_uuid}.png'
        assert get_thumbnail_filename(test_uuid, 'webp') == f'thm_{test_uuid}.webp'

        # Test case insensitive extensions
        assert get_thumbnail_filename(test_uuid, 'JPG') == f'thm_{test_uuid}.JPG'
        assert get_thumbnail_filename(test_uuid, 'PNG') == f'thm_{test_uuid}.PNG'

        # Test edge cases
        assert get_thumbnail_filename(test_uuid, '') == f'thm_{test_uuid}.'
        assert get_thumbnail_filename('', 'jpg') == 'thm_.jpg'

    def test_get_thumbnail_path_direct(self, temp_dir, sample_uuids):
        """Test direct upload thumbnail path generation."""
        test_uuid = sample_uuids[0]

        # Test basic path generation
        path = get_thumbnail_path_direct(test_uuid, 'jpg')
        assert 'thm_' in path
        assert test_uuid in path
        assert path.endswith('.jpg')
        assert 'direct_uploads' in path

        # Test different extensions
        path_png = get_thumbnail_path_direct(test_uuid, 'png')
        assert path_png.endswith('.png')
        assert test_uuid in path_png

        # Test that different UUIDs produce different paths
        different_uuid = sample_uuids[1]
        different_path = get_thumbnail_path_direct(different_uuid, 'jpg')
        assert path != different_path
        assert different_uuid in different_path

    def test_get_thumbnail_path_encounter(self, temp_dir, sample_uuids):
        """Test encounter file thumbnail path generation."""
        test_uuid = sample_uuids[0]
        encounter_file = Path(IMAGE_DIR) / f"{test_uuid}.jpg"

        # Test basic path generation
        path = get_thumbnail_path_encounter(encounter_file)
        path_str = str(path)
        assert 'thm_' in path_str
        assert test_uuid in path_str
        assert path_str.endswith('.jpg')
        assert 'encounter_files' in path_str

        # Test different extensions
        encounter_webp = Path(IMAGE_DIR) / f"{test_uuid}.webp"
        path_webp = get_thumbnail_path_encounter(encounter_webp)
        path_webp_str = str(path_webp)
        assert path_webp_str.endswith('.webp')
        assert test_uuid in path_webp_str

        # Test that direct and encounter paths are different
        direct_path = get_thumbnail_path_direct(test_uuid, 'jpg')
        encounter_path = get_thumbnail_path_encounter(encounter_file)
        direct_path_str = str(direct_path)
        encounter_path_str = str(encounter_path)
        assert direct_path_str != encounter_path_str
        assert 'direct_uploads' in direct_path_str
        assert 'encounter_files' in encounter_path_str

    def test_validate_thumbnail_filename(self):
        """Test thumbnail filename validation."""
        # Valid filenames
        valid_filenames = [
            'thm_12345678-1234-1234-1234-123456789abc.jpg',
            'thm_12345678123412341234123456789abc.png',
            'thm_123e4567-e89b-12d3-a456-426614174000.jpeg',
        ]

        for filename in valid_filenames:
            assert validate_thumbnail_filename(filename) is True, f"Should accept valid filename: {filename}"

        # Invalid filenames
        invalid_filenames = [
            '../../../etc/passwd',
            '../malicious.jpg',
            'not-a-thumbnail.jpg',
            '../../../thm_malicious.jpg',
            '',
            None,
        ]

        for filename in invalid_filenames:
            if filename is not None:
                assert validate_thumbnail_filename(filename) is False, f"Should reject invalid filename: {filename}"

    def test_thumbnail_exists_direct(self, temp_dir, sample_uuids):
        """Test direct upload thumbnail existence checking."""
        test_uuid = sample_uuids[0]
        ext = 'jpg'

        # Test non-existent thumbnail
        path = get_thumbnail_path_direct(test_uuid, ext)
        exists = thumbnail_exists_direct(test_uuid, ext)
        assert exists is False

        # Create a file and test existence
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            f.write('dummy content')

        exists = thumbnail_exists_direct(test_uuid, ext)
        assert exists is True

        # Clean up
        os.remove(path)

    def test_path_generation_with_various_uuids(self, temp_dir, sample_uuids):
        """Test path generation with various UUID formats."""
        for test_uuid in sample_uuids:
            # Test direct upload paths
            direct_path = get_thumbnail_path_direct(test_uuid, 'jpg')
            assert 'thm_' in direct_path
            assert test_uuid in direct_path
            assert direct_path.endswith('.jpg')
            assert 'direct_uploads' in direct_path

            # Test encounter file paths
            encounter_file = Path(IMAGE_DIR) / f"{test_uuid}.png"
            encounter_path = get_thumbnail_path_encounter(encounter_file)
            encounter_path_str = str(encounter_path)
            assert 'thm_' in encounter_path_str
            assert test_uuid in encounter_path_str
            assert encounter_path_str.endswith('.png')
            assert 'encounter_files' in encounter_path_str

            # Paths should be different for different types
            assert direct_path != encounter_path

    def test_filename_validation_edge_cases(self):
        """Test filename validation with edge cases."""
        # Test UUIDs with different formats
        valid_uuids = [
            '12345678-1234-1234-1234-123456789abc',
            '12345678123412341234123456789abc',  # Without dashes
            '123e4567-e89b-12d3-a456-426614174000',  # Different valid UUID
        ]

        for test_uuid in valid_uuids:
            filename = get_thumbnail_filename(test_uuid, 'jpg')
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
            filename = get_thumbnail_filename(invalid_uuid, 'jpg')
            assert filename.startswith('thm_')
            assert filename.endswith('.jpg')

    def test_concurrent_path_operations(self, temp_dir, sample_uuids):
        """Test thread-safe path operations."""
        import threading
        import time

        results = []
        errors = []

        def generate_paths(uuid_idx):
            try:
                test_uuid = sample_uuids[uuid_idx % len(sample_uuids)]
                for i in range(10):  # Generate multiple paths per thread
                    path = get_thumbnail_path_direct(test_uuid, 'jpg')
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
            assert path.startswith('/app')  # Should be absolute path
            assert 'thm_' in path

    def test_different_extensions(self, temp_dir):
        """Test path generation with different file extensions."""
        test_uuid = '12345678-1234-1234-1234-123456789abc'
        extensions = ['jpg', 'jpeg', 'JPG', 'JPEG', 'png', 'webp']

        for ext in extensions:
            path = get_thumbnail_path_direct(test_uuid, ext)
            assert path.endswith(f'.{ext}')
            assert test_uuid in path
            assert 'thm_' in path

    def test_path_consistency(self, temp_dir, sample_uuids):
        """Test that path generation is consistent."""
        test_uuid = sample_uuids[0]
        ext = 'jpg'

        # Generate path multiple times
        path1 = get_thumbnail_path_direct(test_uuid, ext)
        path2 = get_thumbnail_path_direct(test_uuid, ext)
        path3 = get_thumbnail_path_direct(test_uuid, ext)

        # Should be identical
        assert path1 == path2 == path3

        # Same for encounter files
        encounter_file = Path(IMAGE_DIR) / f"{test_uuid}.{ext}"
        epath1 = get_thumbnail_path_encounter(encounter_file)
        epath2 = get_thumbnail_path_encounter(encounter_file)

        assert str(epath1) == str(epath2)

        # But direct and encounter should be different
        assert str(path1) != str(epath1)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
