
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


class TestLosslessJpegStrip:
    """The strip must remove metadata without re-encoding the image."""

    def _photo_with_metadata(self):
        import random

        rng = random.Random(7)
        img = Image.new("RGB", (160, 120))
        img.putdata([(rng.randrange(256), rng.randrange(256), rng.randrange(256)) for _ in range(160 * 120)])
        exif = img.getexif()
        exif[0x010E] = "Sensitive Patient Data"
        out = BytesIO()
        img.save(out, format="JPEG", quality=92, exif=exif, comment=b"patient: Jane")
        return out.getvalue()

    def test_compressed_image_data_is_byte_identical(self):
        original = self._photo_with_metadata()
        clean = strip_exif_data(original)
        scan_start = original.index(b"\xff\xda")
        assert clean[clean.index(b"\xff\xda"):] == original[scan_start:]  # entropy data untouched
        assert len(clean) < len(original)

    def test_decoded_pixels_are_identical_and_size_unchanged(self):
        original = self._photo_with_metadata()
        clean = strip_exif_data(original)
        with Image.open(BytesIO(original)) as before, Image.open(BytesIO(clean)) as after:
            assert after.size == before.size
            assert list(after.getdata()) == list(before.getdata())

    def test_exif_and_comments_are_gone(self):
        clean = strip_exif_data(self._photo_with_metadata())
        assert b"Sensitive Patient Data" not in clean and b"Jane" not in clean
        assert b"Exif\x00\x00" not in clean

    def test_icc_profile_is_kept(self):
        img = Image.new("RGB", (8, 8), "red")
        out = BytesIO()
        icc = b"\x00" * 128
        img.save(out, format="JPEG", icc_profile=icc, exif=Image.Exif())
        assert b"ICC_PROFILE\x00" in strip_exif_data(out.getvalue())

    def test_undecodable_jpeg_is_returned_unchanged(self):
        original = self._photo_with_metadata()
        broken = original[:2] + b"\x00\x00" + original[2:]  # not a valid marker stream
        assert strip_exif_data(broken) == broken  # undecodable: returned unchanged
