"""
Basic Thumbnail System Tests

Simple functional tests that verify the core thumbnail functionality works correctly.
"""

import pytest
import os
import tempfile
import shutil
from pathlib import Path
from PIL import Image

# Import the functions we're testing
from utils.image_processing import generate_thumbnail, get_image_info
from utils.fileUtils import get_thumbnail_filename, get_thumbnail_path_direct


class TestThumbnailBasic:
    """Basic functional tests for thumbnail system."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test files."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def sample_image(self, temp_dir):
        """Create a sample test image."""
        # Create a test image
        image = Image.new('RGB', (400, 300), color='blue')
        image_path = os.path.join(temp_dir, 'test_image.jpg')
        image.save(image_path, 'JPEG', quality=95)
        return image_path

    def test_generate_thumbnail_basic(self, sample_image, temp_dir):
        """Test basic thumbnail generation."""
        output_path = os.path.join(temp_dir, 'thumbnail.jpg')

        # Generate thumbnail
        result = generate_thumbnail(sample_image, output_path)

        # Verify success
        assert result is True
        assert os.path.exists(output_path)

        # Verify thumbnail properties
        with Image.open(output_path) as thumb:
            assert thumb.size == (180, 135)  # Aspect ratio preserved within the 180px box
            assert thumb.format == 'JPEG'

    def test_get_image_info(self, sample_image):
        """Test image information extraction."""
        info = get_image_info(sample_image)

        assert info['format'] == 'JPEG'
        assert info['mode'] == 'RGB'
        assert info['size'] == (400, 300)

    def test_get_thumbnail_filename(self):
        """Test thumbnail filename generation."""
        # Test with UUID-based filename
        uuid_filename = '12345678-1234-1234-1234-123456789abc.jpg'
        thumb_filename = get_thumbnail_filename(uuid_filename)
        assert thumb_filename == 'thm_12345678-1234-1234-1234-123456789abc.jpg'

        # Test with PNG
        png_filename = '12345678-1234-1234-1234-123456789abc.png'
        thumb_filename = get_thumbnail_filename(png_filename)
        assert thumb_filename == 'thm_12345678-1234-1234-1234-123456789abc.png'

        # Test JPEG normalization
        jpeg_filename = '12345678-1234-1234-1234-123456789abc.jpeg'
        thumb_filename = get_thumbnail_filename(jpeg_filename)
        assert thumb_filename == 'thm_12345678-1234-1234-1234-123456789abc.jpg'

    def test_get_thumbnail_path_direct(self):
        """Test direct upload thumbnail path generation."""
        test_uuid = '12345678-1234-1234-1234-123456789abc'
        ext = 'jpg'

        path = get_thumbnail_path_direct(test_uuid, ext)

        # Verify path components
        path_str = str(path)
        assert 'thm_' in path_str
        assert test_uuid in path_str
        assert 'direct_uploads' in path_str
        assert path_str.startswith('/app')  # Should be absolute path

    def test_thumbnail_custom_size(self, sample_image, temp_dir):
        """Test thumbnail generation with custom size."""
        output_path = os.path.join(temp_dir, 'custom_thumb.jpg')

        # Generate thumbnail with custom size
        result = generate_thumbnail(sample_image, output_path, size=(100, 100))

        assert result is True
        assert os.path.exists(output_path)

        with Image.open(output_path) as thumb:
            assert thumb.size == (100, 75)  # Aspect ratio preserved within the 100px box

    def test_thumbnail_custom_quality(self, sample_image, temp_dir):
        """Test thumbnail generation with custom quality."""
        output_path = os.path.join(temp_dir, 'quality_thumb.jpg')

        # Generate thumbnail with custom quality
        result = generate_thumbnail(sample_image, output_path, quality=50)

        assert result is True
        assert os.path.exists(output_path)

        # Lower quality should produce smaller file
        original_size = os.path.getsize(sample_image)
        thumb_size = os.path.getsize(output_path)
        assert thumb_size < original_size

    def test_generate_thumbnail_various_formats(self, temp_dir):
        """Test thumbnail generation from different image formats."""
        formats_to_test = [
            ('JPEG', (400, 300), 'red'),
            ('PNG', (400, 300), 'blue'),
            ('GIF', (200, 150), 'green'),
        ]

        for format_name, size, color in formats_to_test:
            # Create test image
            if format_name == 'PNG':
                # Convert color string to RGB tuple for PNG
                color_map = {'red': (255, 0, 0), 'blue': (0, 0, 255), 'green': (0, 128, 0)}
                rgb_color = color_map.get(color, (128, 128, 128))
                image = Image.new('RGBA', size, color=(*rgb_color, 255))  # Add alpha for PNG
            else:
                image = Image.new('RGB', size, color=color)

            source_path = os.path.join(temp_dir, f'test.{format_name.lower()}')
            output_path = os.path.join(temp_dir, f'thumb_{format_name.lower()}.jpg')

            image.save(source_path, format_name)

            # Generate thumbnail
            result = generate_thumbnail(source_path, output_path)

            assert result is True, f"Failed to generate thumbnail from {format_name}"
            assert os.path.exists(output_path)

            # Verify output is always JPEG, aspect preserved
            with Image.open(output_path) as thumb:
                assert thumb.size == (180, 135)
                assert thumb.format == 'JPEG'

    def test_error_handling(self, temp_dir):
        """Test error handling for invalid inputs."""
        output_path = os.path.join(temp_dir, 'output.jpg')

        # Test with non-existent source file
        result = generate_thumbnail('/nonexistent/path.jpg', output_path)
        assert result is False
        assert not os.path.exists(output_path)

        # Test with invalid output path
        invalid_output = '/nonexistent/directory/thumb.jpg'
        result = generate_thumbnail(temp_dir + '/nonexistent.jpg', invalid_output)
        assert result is False

    def test_aspect_ratio_handling(self, temp_dir):
        """Test that the aspect ratio is preserved within the size box."""
        # Test portrait image
        portrait = Image.new('RGB', (400, 800), color='purple')
        portrait_path = os.path.join(temp_dir, 'portrait.jpg')
        portrait.save(portrait_path, 'JPEG')

        output_path = os.path.join(temp_dir, 'portrait_thumb.jpg')
        result = generate_thumbnail(portrait_path, output_path)

        assert result is True
        with Image.open(output_path) as thumb:
            assert thumb.size == (90, 180)  # Aspect preserved within the 180px box

        # Test landscape image
        landscape = Image.new('RGB', (1200, 600), color='orange')
        landscape_path = os.path.join(temp_dir, 'landscape.jpg')
        landscape.save(landscape_path, 'JPEG')

        output_path = os.path.join(temp_dir, 'landscape_thumb.jpg')
        result = generate_thumbnail(landscape_path, output_path)

        assert result is True
        with Image.open(output_path) as thumb:
            assert thumb.size == (180, 90)  # Aspect preserved within the 180px box


if __name__ == '__main__':
    pytest.main([__file__, '-v'])