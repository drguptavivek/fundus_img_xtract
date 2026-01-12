
import pytest
from PIL import Image
from io import BytesIO
from utils.image_processing import strip_exif_data

class TestExifStripping:
    """Test suite for image metadata removal."""

    def create_test_image_with_exif(self):
        """Helper to create an image with dummy EXIF data."""
        # Create a simple image
        img = Image.new('RGB', (100, 100), color='red')
        
        # Add some EXIF data
        # 0x010E is ImageDescription
        exif_data = img.getexif()
        exif_data[0x010E] = "Sensitive Patient Data"
        
        byte_arr = BytesIO()
        img.save(byte_arr, format='JPEG', exif=exif_data)
        return byte_arr.getvalue()

    def test_strip_exif_removes_metadata(self):
        """Test that strip_exif_data removes EXIF tags."""
        original_bytes = self.create_test_image_with_exif()
        
        # Verify original has EXIF
        with Image.open(BytesIO(original_bytes)) as img:
            exif = img.getexif()
            assert exif[0x010E] == "Sensitive Patient Data"
            
        # Strip metadata
        clean_bytes = strip_exif_data(original_bytes)
        
        # Verify cleaned image has no EXIF
        with Image.open(BytesIO(clean_bytes)) as img:
            exif = img.getexif()
            # method 1: check specific tag is gone
            assert 0x010E not in exif
            # method 2: check it's strictly empty or minimal
            # Some libraries might leave basic structural tags, 
            # so we focus on the sensitive tag being gone.

    def test_strip_exif_preserves_image_integrity(self):
        """Test that the image is still valid and looks same-ish."""
        original_bytes = self.create_test_image_with_exif()
        clean_bytes = strip_exif_data(original_bytes)
        
        assert len(clean_bytes) > 0
        
        with Image.open(BytesIO(clean_bytes)) as img:
            assert img.format == 'JPEG'
            assert img.size == (100, 100)
            
    def test_strip_exif_handles_empty_input(self):
        """Test handling of empty or None input."""
        assert strip_exif_data(b"") == b""
        assert strip_exif_data(None) is None
    
    def test_strip_exif_handles_invalid_image(self):
        """Test that invalid image data is returned as-is (fail open/safe)."""
        garbage = b"not an image"
        # Function catches exception and returns original
        assert strip_exif_data(garbage) == garbage
