
import pytest
import re
from utils.filename_utils import sanitize_export_filename

class TestFilenameUtils:
    
    def test_sanitize_basic(self):
        """Test basic filename sanitization."""
        name = sanitize_export_filename("My Export File", "csv", include_timestamp=False)
        assert name == "My_Export_File.csv"
        
    def test_sanitize_special_chars(self):
        """Test removal of special characters."""
        name = sanitize_export_filename("user@example.com export!", "xlsx", include_timestamp=False)
        # secure_filename removes @ and !, space becomes underscore
        assert name == "userexample_com_export.xlsx"
        
    def test_sanitize_path_traversal(self):
        """Test prevention of path traversal."""
        name = sanitize_export_filename("../../../etc/passwd", "txt", include_timestamp=False)
        # secure_filename cleans this up, and our regex further solidifies it
        assert ".." not in name
        assert "/" not in name
        assert name.endswith(".txt")
        
    def test_timestamp_and_uuid(self):
        """Test timestamp and UUID inclusion."""
        name = sanitize_export_filename("data", "json", include_timestamp=True)
        # Pattern: data_YYYYMMDD_HHMMSS_8charUUID.json
        # Check basic structure using regex
        pattern = r"^data_\d{8}_\d{6}_[a-f0-9]{8}\.json$"
        assert re.match(pattern, name), f"Filename {name} did not match expected pattern"

    def test_empty_input_fallback(self):
        """Test fallback for empty inputs."""
        name = sanitize_export_filename("", "", include_timestamp=False)
        assert name == "export.dat"
        
    def test_pii_like_input(self):
        """Test handling of inputs that might look like PII formatting."""
        # e.g. "John Doe (Patient)"
        name = sanitize_export_filename("John Doe (Patient)", "zip", include_timestamp=False)
        assert name == "John_Doe_Patient.zip"
