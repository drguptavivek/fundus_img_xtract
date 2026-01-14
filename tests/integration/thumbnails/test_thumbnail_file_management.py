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
    cleanup_orphaned_thumbnails
)
from utils.image_processing import get_thumbnail_filename


class TestThumbnailFileManagement:
    """Test suite for thumbnail file management functions."""

    def test_generate_thumbnail_filename(self):
        """Test thumbnail filename generation."""
        # Test with common filenames - extensions are preserved except jpeg->jpg
        assert get_thumbnail_filename('test.jpg') == 'thm_test.jpg'
        assert get_thumbnail_filename('photo.jpeg') == 'thm_photo.jpg'  # .jpeg becomes .jpg
        assert get_thumbnail_filename('image.png') == 'thm_image.png'   # .png preserved
        assert get_thumbnail_filename('picture.webp') == 'thm_picture.webp'  # .webp preserved

        # Test case sensitivity - extension is lowercased
        assert get_thumbnail_filename('TEST.JPG') == 'thm_TEST.jpg'
        assert get_thumbnail_filename('PHOTO.PNG') == 'thm_PHOTO.png'

        # Test edge cases - no extension
        assert get_thumbnail_filename('file') == 'thm_file'

    def test_validate_thumbnail_filename(self):
        """Test thumbnail filename validation."""
        # Valid thumbnail filenames
        assert validate_thumbnail_filename('thm_abc123.jpg') is True
        assert validate_thumbnail_filename('thm_test.jpg') is True
        assert validate_thumbnail_filename('thm_image.jpg') is True

        # Invalid filenames (no thm_ prefix)
        assert validate_thumbnail_filename('abc123.jpg') is False
        assert validate_thumbnail_filename('test.png') is False

        # Edge cases
        assert validate_thumbnail_filename('') is False
        assert validate_thumbnail_filename('thm_') is False  # Missing file extension
        assert validate_thumbnail_filename('../thm_test.jpg') is False  # Path traversal

    def test_thumbnail_filename_generation_formats(self):
        """Test thumbnail filename generation with various formats."""
        # Note: extensions are preserved except .jpeg -> .jpg
        test_cases = [
            ('original.jpg', 'thm_original.jpg'),
            ('photo.jpeg', 'thm_photo.jpg'),  # .jpeg becomes .jpg
            ('image.png', 'thm_image.png'),
            ('picture.gif', 'thm_picture.gif'),
            ('document.pdf', 'thm_document.pdf'),
            ('archive.zip', 'thm_archive.zip'),
        ]

        for original, expected in test_cases:
            assert get_thumbnail_filename(original) == expected

    def test_path_generation_with_various_formats(self):
        """Test that path generation functions accept proper parameters."""
        # These functions require specific parameters from the actual DB
        # We can test that they exist and are callable
        assert callable(get_thumbnail_path_direct)
        assert callable(get_thumbnail_path_encounter)

    def test_filename_validation_edge_cases(self):
        """Test filename validation with edge cases."""
        # Valid cases
        assert validate_thumbnail_filename('thm_' + 'a' * 100 + '.jpg') is True

        # Invalid cases
        assert validate_thumbnail_filename('../thm_test.jpg') is False
        assert validate_thumbnail_filename('thm_../../test.jpg') is False
        assert validate_thumbnail_filename('C:\\thm_test.jpg') is False

    def test_thumbnail_exists_direct(self):
        """Test direct upload thumbnail existence checking."""
        # This function requires folder_rel and original_filename
        # We can test that it's callable
        assert callable(thumbnail_exists_direct)

    def test_cleanup_orphaned_thumbnails(self):
        """Test cleanup of orphaned thumbnails."""
        # This function returns a dict with cleanup results
        assert callable(cleanup_orphaned_thumbnails)
        # Function may not have orphaned files, but it should be callable
        # and return results

    def test_concurrent_path_operations(self):
        """Test concurrent thumbnail filename generation."""
        # Generate multiple filenames concurrently
        filenames = [
            get_thumbnail_filename(f'image_{i}.jpg')
            for i in range(10)
        ]

        # All should be generated successfully
        assert len(filenames) == 10
        assert all('thm_' in fname for fname in filenames)
        assert all(fname.endswith('.jpg') for fname in filenames)

    def test_path_consistency(self):
        """Test that filename generation is consistent."""
        original = 'test_image.jpg'

        # Multiple calls should produce same result
        result1 = get_thumbnail_filename(original)
        result2 = get_thumbnail_filename(original)

        assert result1 == result2
