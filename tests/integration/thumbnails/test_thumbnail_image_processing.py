"""
Unit Tests for Thumbnail Image Processing

Tests for the core image processing functionality including:
- Thumbnail generation with various formats and sizes
- Error handling for invalid inputs
- Quality and compression settings
- Aspect ratio preservation and center cropping
"""

import pytest
import os
import tempfile
import shutil
from PIL import Image, ImageOps
from pathlib import Path
import io

# Import the functions we're testing
from utils.image_processing import generate_thumbnail, is_supported_image_format, get_image_info


class TestImageProcessing:
    """Test suite for image processing functions."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test images."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def sample_images(self, temp_dir):
        """Create sample test images in various formats."""
        images = {}

        # Create test images with different sizes and formats
        test_configs = [
            ('square.jpg', (500, 500), 'RGB', 'JPEG'),
            ('portrait.jpg', (400, 800), 'RGB', 'JPEG'),
            ('landscape.jpg', (1200, 600), 'RGB', 'JPEG'),
            ('png_image.png', (600, 400), 'RGBA', 'PNG'),
            ('webp_image.webp', (800, 800), 'RGB', 'WEBP'),
            ('small.gif', (50, 50), 'RGB', 'GIF'),
            ('large_bmp.bmp', (2000, 1500), 'RGB', 'BMP'),
        ]

        for filename, size, mode, format_name in test_configs:
            image = Image.new(mode, size, color='red')
            if mode == 'RGBA':
                # Add transparent areas for PNG testing
                pixels = image.load()
                for i in range(0, size[0], 20):
                    for j in range(0, size[1], 20):
                        if (i + j) % 40 == 0:
                            pixels[i, j] = (255, 0, 0, 128)  # Semi-transparent red

            file_path = os.path.join(temp_dir, filename)
            image.save(file_path, format_name)
            images[filename] = {
                'path': file_path,
                'size': size,
                'mode': mode,
                'format': format_name
            }

        return images

    def test_generate_thumbnail_basic(self, sample_images, temp_dir):
        """Test basic thumbnail generation."""
        source_path = sample_images['square.jpg']['path']
        output_path = os.path.join(temp_dir, 'thumbnail.jpg')

        # Generate thumbnail
        result = generate_thumbnail(source_path, output_path)

        assert result is True
        assert os.path.exists(output_path)

        # Verify thumbnail properties
        with Image.open(output_path) as thumb:
            assert thumb.size == (180, 180)  # Default size
            assert thumb.format == 'JPEG'

    def test_generate_thumbnail_custom_size(self, sample_images, temp_dir):
        """Test thumbnail generation with custom size."""
        source_path = sample_images['landscape.jpg']['path']
        output_path = os.path.join(temp_dir, 'custom_thumb.jpg')

        # Generate thumbnail with custom size
        result = generate_thumbnail(source_path, output_path, size=(100, 100))

        assert result is True
        assert os.path.exists(output_path)

        with Image.open(output_path) as thumb:
            assert thumb.size == (100, 100)

    def test_generate_thumbnail_custom_quality(self, sample_images, temp_dir):
        """Test thumbnail generation with custom quality."""
        source_path = sample_images['square.jpg']['path']
        output_path = os.path.join(temp_dir, 'quality_thumb.jpg')

        # Generate thumbnail with custom quality
        result = generate_thumbnail(source_path, output_path, quality=50)

        assert result is True
        assert os.path.exists(output_path)

        # Verify file is smaller due to lower quality
        original_size = os.path.getsize(source_path)
        thumb_size = os.path.getsize(output_path)
        assert thumb_size < original_size

    def test_generate_thumbnail_aspect_ratio_preservation(self, sample_images, temp_dir):
        """Test that aspect ratio is preserved with center cropping."""
        # Test portrait image
        source_path = sample_images['portrait.jpg']['path']  # 400x800
        output_path = os.path.join(temp_dir, 'portrait_thumb.jpg')

        result = generate_thumbnail(source_path, output_path)
        assert result is True

        with Image.open(output_path) as thumb:
            assert thumb.size == (180, 180)  # Should be square

        # Test landscape image
        source_path = sample_images['landscape.jpg']['path']  # 1200x600
        output_path = os.path.join(temp_dir, 'landscape_thumb.jpg')

        result = generate_thumbnail(source_path, output_path)
        assert result is True

        with Image.open(output_path) as thumb:
            assert thumb.size == (180, 180)  # Should be square

    def test_generate_thumbnail_various_formats(self, sample_images, temp_dir):
        """Test thumbnail generation from different image formats."""
        formats_to_test = ['square.jpg', 'png_image.png', 'webp_image.webp', 'small.gif']

        for format_name in formats_to_test:
            source_path = sample_images[format_name]['path']
            output_path = os.path.join(temp_dir, f'thumb_{format_name}.jpg')

            result = generate_thumbnail(source_path, output_path)

            assert result is True, f"Failed to generate thumbnail from {format_name}"
            assert os.path.exists(output_path)

            # Verify output is always JPEG for thumbnails
            with Image.open(output_path) as thumb:
                assert thumb.size == (180, 180)
                assert thumb.format == 'JPEG'

    def test_generate_thumbnail_transparent_png(self, sample_images, temp_dir):
        """Test thumbnail generation from transparent PNG."""
        source_path = sample_images['png_image.png']['path']  # RGBA format
        output_path = os.path.join(temp_dir, 'transparent_thumb.jpg')

        result = generate_thumbnail(source_path, output_path)

        assert result is True
        assert os.path.exists(output_path)

        with Image.open(output_path) as thumb:
            assert thumb.size == (180, 180)
            assert thumb.mode == 'RGB'  # Should be converted to RGB
            assert thumb.format == 'JPEG'

    def test_generate_thumbnail_large_image(self, sample_images, temp_dir):
        """Test thumbnail generation from large image."""
        source_path = sample_images['large_bmp.bmp']['path']  # 2000x1500
        output_path = os.path.join(temp_dir, 'large_thumb.jpg')

        result = generate_thumbnail(source_path, output_path)

        assert result is True
        assert os.path.exists(output_path)

        # Verify memory efficiency - thumbnail should be much smaller
        original_size = os.path.getsize(source_path)
        thumb_size = os.path.getsize(output_path)
        assert thumb_size < original_size * 0.1  # Should be at least 10x smaller

    def test_generate_thumbnail_invalid_source(self, temp_dir):
        """Test error handling for invalid source path."""
        non_existent_path = os.path.join(temp_dir, 'does_not_exist.jpg')
        output_path = os.path.join(temp_dir, 'output.jpg')

        result = generate_thumbnail(non_existent_path, output_path)

        assert result is False
        assert not os.path.exists(output_path)

    def test_generate_thumbnail_invalid_output_path(self, sample_images):
        """Test error handling for invalid output path."""
        source_path = sample_images['square.jpg']['path']
        invalid_output_path = '/nonexistent/directory/thumb.jpg'

        result = generate_thumbnail(source_path, invalid_output_path)

        assert result is False

    def test_generate_thumbnail_corrupted_image(self, temp_dir):
        """Test error handling for corrupted image files."""
        # Create a corrupted image file (just write random bytes)
        corrupted_path = os.path.join(temp_dir, 'corrupted.jpg')
        with open(corrupted_path, 'wb') as f:
            f.write(b'This is not a valid image file')

        output_path = os.path.join(temp_dir, 'output.jpg')
        result = generate_thumbnail(corrupted_path, output_path)

        assert result is False
        assert not os.path.exists(output_path)

    def test_is_supported_image_format(self, sample_images):
        """Test image format validation."""
        # Valid formats
        assert is_supported_image_format('image/jpeg') is True
        assert is_supported_image_format('image/png') is True
        assert is_supported_image_format('image/webp') is True
        assert is_supported_image_format('image/gif') is True
        assert is_supported_image_format('image/bmp') is True

        # Invalid formats
        assert is_supported_image_format('application/pdf') is False
        assert is_supported_image_format('text/plain') is False
        assert is_supported_image_format('video/mp4') is False
        assert is_supported_image_format('') is False
        assert is_supported_image_format(None) is False
        assert is_supported_image_format('not-a-format') is False

    def test_get_image_info(self, sample_images):
        """Test image information extraction."""
        # Test JPEG image
        jpeg_info = get_image_info(sample_images['square.jpg']['path'])
        assert jpeg_info['format'] == 'JPEG'
        assert jpeg_info['mode'] == 'RGB'
        assert jpeg_info['size'] == (500, 500)

        # Test PNG image
        png_info = get_image_info(sample_images['png_image.png']['path'])
        assert png_info['format'] == 'PNG'
        assert png_info['mode'] == 'RGBA'
        assert png_info['size'] == (600, 400)

        # Test non-existent file
        with pytest.raises(Exception):
            get_image_info('/nonexistent/path.jpg')

    def test_generate_thumbnail_overwrite_existing(self, sample_images, temp_dir):
        """Test that existing thumbnails are overwritten."""
        source_path = sample_images['square.jpg']['path']
        output_path = os.path.join(temp_dir, 'existing_thumb.jpg')

        # Create initial thumbnail
        result1 = generate_thumbnail(source_path, output_path)
        assert result1 is True

        initial_size = os.path.getsize(output_path)
        initial_mtime = os.path.getmtime(output_path)

        # Wait a bit to ensure different timestamp
        import time
        time.sleep(0.1)

        # Generate again (should overwrite)
        result2 = generate_thumbnail(source_path, output_path)
        assert result2 is True

        # File should be updated
        final_mtime = os.path.getmtime(output_path)
        assert final_mtime > initial_mtime

    def test_generate_thumbnail_edge_cases(self, temp_dir):
        """Test edge cases and boundary conditions."""
        # Create very small image (1x1 pixel)
        tiny_image = Image.new('RGB', (1, 1), color='blue')
        tiny_path = os.path.join(temp_dir, 'tiny.jpg')
        tiny_image.save(tiny_path, 'JPEG')

        output_path = os.path.join(temp_dir, 'tiny_thumb.jpg')
        result = generate_thumbnail(tiny_path, output_path)

        assert result is True
        assert os.path.exists(output_path)

        with Image.open(output_path) as thumb:
            assert thumb.size == (180, 180)  # Should still be 180x180

        # Create very large aspect ratio image
        wide_image = Image.new('RGB', (5000, 100), color='green')
        wide_path = os.path.join(temp_dir, 'wide.jpg')
        wide_image.save(wide_path, 'JPEG')

        output_path = os.path.join(temp_dir, 'wide_thumb.jpg')
        result = generate_thumbnail(wide_path, output_path)

        assert result is True
        assert os.path.exists(output_path)

        with Image.open(output_path) as thumb:
            assert thumb.size == (180, 180)

    def test_generate_thumbnail_memory_efficiency(self, sample_images, temp_dir):
        """Test that thumbnail generation is memory efficient."""
        import psutil
        import os

        # Get process memory before
        process = psutil.Process(os.getpid())
        memory_before = process.memory_info().rss

        # Generate thumbnails for all test images
        for image_name in sample_images:
            source_path = sample_images[image_name]['path']
            output_path = os.path.join(temp_dir, f'efficiency_test_{image_name}_thumb.jpg')
            result = generate_thumbnail(source_path, output_path)
            assert result is True

        # Check memory didn't grow excessively
        memory_after = process.memory_info().rss
        memory_growth = memory_after - memory_before

        # Memory growth should be reasonable (less than 50MB for this test)
        assert memory_growth < 50 * 1024 * 1024, f"Memory grew by {memory_growth / 1024 / 1024:.1f}MB"

    def test_generate_thumbnail_quality_settings(self, sample_images, temp_dir):
        """Test different quality settings and their effects."""
        source_path = sample_images['square.jpg']['path']

        qualities = [10, 50, 85, 95, 100]
        file_sizes = {}

        for quality in qualities:
            output_path = os.path.join(temp_dir, f'quality_{quality}.jpg')
            result = generate_thumbnail(source_path, output_path, quality=quality)

            assert result is True
            assert os.path.exists(output_path)

            file_sizes[quality] = os.path.getsize(output_path)

        # Higher quality should generally result in larger files
        assert file_sizes[10] < file_sizes[50] < file_sizes[85]

        # Quality 100 should be largest
        assert file_sizes[100] >= file_sizes[95]

    def test_generate_thumbnail_different_extensions(self, sample_images, temp_dir):
        """Test thumbnail generation with different output extensions."""
        source_path = sample_images['square.jpg']['path']

        extensions = ['.jpg', '.jpeg', '.JPG', '.JPEG']

        for ext in extensions:
            output_path = os.path.join(temp_dir, f'test{ext}')
            result = generate_thumbnail(source_path, output_path)

            assert result is True
            assert os.path.exists(output_path)

            with Image.open(output_path) as thumb:
                assert thumb.size == (180, 180)
                assert thumb.format == 'JPEG'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])