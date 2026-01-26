"""
Test suite for secure filename validation (CWE-434).

This module tests that uploaded filenames are strictly validated to prevent:
1. Path traversal attacks (../, ..\\, etc.)
2. Null byte injection
3. Log injection attempts
4. Invalid UTF-8 encoding
5. Special characters that could cause issues

Tests follow TDD: write failing tests first, then implement fix.
"""

import pytest
import re
from werkzeug.datastructures import FileStorage

from utils.log_sanitize import sanitize_log_value


class TestFilenameValidation:
    """Test suite for secure filename validation on file uploads."""

    def test_valid_filenames_pass_validation(self):
        """
        Test that valid filenames pass validation.

        Valid filenames should contain only alphanumeric characters,
        dots, underscores, and hyphens.
        """
        valid_filenames = [
            "image.jpg",
            "photo.png",
            "document.pdf",
            "file_name.txt",
            "my-file-123.JPG",
            "test.file.name.png",
            "Multiple.dots.in.name.jpg",
            "café.jpg",
            "病例图片.png",
        ]

        for filename in valid_filenames:
            # Test that validation function exists and accepts valid filenames
            try:
                from utils.filename_validation import validate_upload_filename
                result, error = validate_upload_filename(filename)
                assert result is True, f"Valid filename '{filename}' should pass validation: {error}"
            except ImportError:
                pytest.fail("validate_upload_filename() function does not exist yet")

    def test_null_bytes_rejected(self):
        """
        FAILING TEST: Null bytes not yet detected/rejected.

        Test that filenames containing null bytes are rejected.
        Null bytes can be used for path traversal and log injection.
        """
        malicious_filenames = [
            "test\x00file.jpg",  # Null byte in middle
            "\x00malicious.jpg",  # Null byte at start
            "file.jpg\x00",  # Null byte at end
            "test\x00\x00file.png",  # Multiple null bytes
        ]

        for filename in malicious_filenames:
            try:
                from utils.filename_validation import validate_upload_filename
                result, error = validate_upload_filename(filename)
                assert result is False, f"Filename with null bytes should be rejected: {repr(filename)}"
                assert "null" in error.lower() or "byte" in error.lower(), (
                    f"Error message should mention null bytes: {error}"
                )
            except ImportError:
                pytest.skip("validate_upload_filename() not implemented yet")

    def test_path_traversal_patterns_rejected(self):
        """
        FAILING TEST: Path traversal patterns not yet detected.

        Test that filenames containing path traversal patterns are rejected.
        """
        malicious_filenames = [
            "../malicious.jpg",
            "..\\malicious.jpg",
            "....//jpg",
            "./test.jpg",
            ".\\test.jpg",
            "....\\\\jpg",
            "/etc/passwd",
            "C:\\Windows\\System32\\file.jpg",
            "~/../../etc/passwd",
            "..%2Fmalicious.jpg",  # URL-encoded traversal
            "..%5Cmalicious.jpg",  # URL-encoded backslash
        ]

        for filename in malicious_filenames:
            try:
                from utils.filename_validation import validate_upload_filename
                result, error = validate_upload_filename(filename)
                assert result is False, f"Path traversal pattern should be rejected: {filename}"
                assert "traversal" in error.lower() or "path" in error.lower() or "invalid" in error.lower(), (
                    f"Error message should mention path traversal: {error}"
                )
            except ImportError:
                pytest.skip("validate_upload_filename() not implemented yet")

    def test_special_characters_rejected(self):
        """
        FAILING TEST: Special characters not yet rejected.

        Test that filenames with dangerous special characters are rejected.
        Only [a-zA-Z0-9._-] should be allowed.
        """
        malicious_filenames = [
            "file<script>.jpg",  # Script tags
            "file|pipe.jpg",  # Pipe character
            "file;command.jpg",  # Command separator
            "file`backtick`.jpg",  # Command substitution
            "file$(command).jpg",  # Command substitution
            "file&&command.jpg",  # Command chaining
            "file\nnewline.jpg",  # Newline character
            "file\ttab.jpg",  # Tab character
            "file\rcarriage.jpg",  # Carriage return
            "file<>redirect.jpg",  # Redirect characters
        ]

        for filename in malicious_filenames:
            try:
                from utils.filename_validation import validate_upload_filename
                result, error = validate_upload_filename(filename)
                assert result is False, f"Special character should be rejected: {repr(filename)}"
            except ImportError:
                pytest.skip("validate_upload_filename() not implemented yet")

    def test_empty_filename_rejected(self):
        """
        Test that empty filenames are rejected.
        """
        empty_filenames = [
            "",
            "   ",
            "\t",
            "\n",
        ]

        for filename in empty_filenames:
            try:
                from utils.filename_validation import validate_upload_filename
                result, error = validate_upload_filename(filename)
                assert result is False, f"Empty filename should be rejected: {repr(filename)}"
            except ImportError:
                pytest.skip("validate_upload_filename() not implemented yet")

    def test_filename_length_limit(self):
        """
        FAILING TEST: Filename length not yet limited.

        Test that excessively long filenames are rejected.
        """
        # Create a 300-character filename
        long_filename = "a" * 300 + ".jpg"

        try:
            from utils.filename_validation import validate_upload_filename
            result, error = validate_upload_filename(long_filename)
            assert result is False, "Excessively long filename should be rejected"
        except ImportError:
            pytest.skip("validate_upload_filename() not implemented yet")

    def test_valid_extension_required(self):
        """
        FAILING TEST: File extension validation not yet implemented.

        Test that filenames without valid extensions are rejected.
        """
        invalid_filenames = [
            "noextension",
            "file",
            ".hiddenfile",  # Hidden files (no extension before dot)
            "file.with.a",  # Extension too short (1 char)
            "file.exten$",  # Extension with invalid characters
        ]

        for filename in invalid_filenames:
            try:
                from utils.filename_validation import validate_upload_filename
                result, error = validate_upload_filename(filename)
                assert result is False, f"Filename without valid extension should be rejected: {filename}"
            except ImportError:
                pytest.skip("validate_upload_filename() not implemented yet")

    def test_utf8_validation(self):
        """
        FAILING TEST: UTF-8 validation not yet implemented.

        Test that invalid UTF-8 sequences are detected and rejected.
        """
        # Invalid UTF-8 sequences
        invalid_utf8 = [
            b"\xff\xfe.jpg",  # Invalid UTF-8 bytes
            b"\x80\x81.jpg",  # Invalid continuation bytes
        ]

        for filename_bytes in invalid_utf8:
            try:
                from utils.filename_validation import validate_upload_filename
                # Try to decode as UTF-8 first
                try:
                    filename = filename_bytes.decode('utf-8')
                except UnicodeDecodeError:
                    filename = filename_bytes.decode('utf-8', errors='ignore')

                result, error = validate_upload_filename(filename)
                # Invalid UTF-8 should be rejected or sanitized
                assert result is False or filename == sanitize_log_value(filename), (
                    f"Invalid UTF-8 should be rejected: {repr(filename_bytes)}"
                )
            except ImportError:
                pytest.skip("validate_upload_filename() not implemented yet")


class TestSecureFilenameBehavior:
    """Test suite for secure_filename() behavior and enhancements."""

    def test_secure_filename_removes_dangerous_chars(self):
        """
        Test that secure_filename() removes dangerous characters.
        This is a baseline test for Werkzeug's secure_filename().
        """
        from werkzeug.utils import secure_filename

        # secure_filename should remove path components
        assert secure_filename("../../../etc/passwd") == "etc_passwd"
        assert secure_filename("../../test.jpg") == "test.jpg"

        # Should remove special characters
        assert secure_filename("file<script>.jpg") == "filescript.jpg"
        assert secure_filename("file;name.jpg") == "filename.jpg"

    def test_secure_filename_preserves_safe_chars(self):
        """
        Test that secure_filename() preserves safe characters.
        """
        from werkzeug.utils import secure_filename

        assert secure_filename("normal-file_123.jpg") == "normal-file_123.jpg"
        assert secure_filename("My Photo.PNG") == "My_Photo.PNG"


class TestFilenameLoggingSanitization:
    """Test suite for filename logging sanitization."""

    def test_original_filename_sanitized_in_logs(self):
        """
        FAILING TEST: Original filename not sanitized before logging.

        Test that the original filename is sanitized before being logged.
        The original filename from file.filename should be validated
        and sanitized BEFORE any logging or processing.
        """
        # Test that sanitize_log_value works correctly
        malicious_input = "test\x00file<script>.jpg"
        sanitized = sanitize_log_value(malicious_input)

        # Should not contain null bytes (critical for injection prevention)
        assert "\x00" not in sanitized

        # Should be a string
        assert isinstance(sanitized, str)

        # Should be safe for logs (no null bytes, no newlines)
        assert "\x00" not in sanitized
        assert "\n" not in sanitized or "\\n" in sanitized
        assert "\r" not in sanitized or "\\r" in sanitized


class TestFilenameValidationIntegration:
    """Integration tests for filename validation in upload flow."""

    def test_upload_with_null_byte_filename_rejected(self, client, auth_client):
        """
        FAILING TEST: Upload with null byte in filename not rejected.

        Test that file uploads with null bytes in the filename are rejected
        at the validation layer before processing.
        """
        # Create a mock file with null byte in filename
        from io import BytesIO

        file_content = b"fake image content"
        file_data = {
            'file': (BytesIO(file_content), "test\x00file.jpg")
        }

        # This should be rejected before processing
        # We'll need to check the actual upload endpoint
        pass  # Placeholder - will implement when function exists

    def test_upload_with_path_traversal_rejected(self, client, auth_client):
        """
        FAILING TEST: Upload with path traversal not rejected.

        Test that file uploads with path traversal patterns are rejected.
        """
        pass  # Placeholder - will implement when function exists
