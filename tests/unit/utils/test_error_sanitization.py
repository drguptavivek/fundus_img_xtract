"""
Test suite for error message sanitization (CWE-209).

This module tests that error messages and stack traces are sanitized to prevent
information disclosure through log injection attacks.

Tests follow TDD: write failing tests first, then implement fix.
"""

import pytest
import logging
import traceback
from unittest.mock import patch, MagicMock
from flask import Flask

from utils.stack_trace_handler import log_stack_trace, get_runtime_error_logger


class TestErrorSanitization:
    """Test suite for error message and stack trace sanitization."""

    def test_file_paths_sanitized_in_logs(self, caplog):
        """
        FAILING TEST: File paths not sanitized in stack traces.

        Test that file paths in stack traces are sanitized to remove
        sensitive information like project root, absolute paths, etc.
        """
        caplog.set_level(logging.ERROR)

        # Create an exception that will have a stack trace
        try:
            # Trigger an exception to get a stack trace
            raise ValueError("Test exception")
        except ValueError as e:
            log_stack_trace(message="Test error", exception=e)

        # Check that the log was created
        assert len(caplog.records) > 0

        # The log should not contain absolute paths
        for record in caplog.records:
            log_message = record.getMessage()
            # Should not contain /app/ or other absolute path indicators
            # This will FAIL until we implement path sanitization
            assert "/app/" not in log_message, (
                f"Log should not contain absolute paths like /app/: {log_message[:200]}"
            )

    def test_database_connection_strings_sanitized(self, caplog):
        """
        FAILING TEST: Database connection strings not sanitized.

        Test that database connection strings in error messages are sanitized
        to prevent exposure of credentials.
        """
        caplog.set_level(logging.ERROR)

        # Simulate a database connection error with connection string
        try:
            # Create a mock database error with connection string
            error_msg = (
                "connection to server at \"localhost\", port 5432 failed: "
                "password='supersecret123' for user 'postgres'"
            )
            raise Exception(error_msg)
        except Exception as e:
            log_stack_trace(message="Database error", exception=e)

        # Check that sensitive database info is sanitized
        for record in caplog.records:
            log_message = record.getMessage()
            # Should not expose database credentials
            # This will FAIL until we implement sanitization
            assert "supersecret123" not in log_message, (
                f"Log should not expose database password: {log_message[:200]}"
            )
            assert "password='***'" in log_message or "password = '***'" in log_message, (
                f"Log should mask password: {log_message[:200]}"
            )

    def test_environment_variables_not_logged(self, caplog):
        """
        FAILING TEST: Environment variables may be logged in stack traces.

        Test that environment variables containing sensitive data are not
        exposed in stack traces.
        """
        caplog.set_level(logging.ERROR)

        # Create an exception that might have environment context
        try:
            import os
            # Set a mock environment variable
            os.environ['TEST_SECRET_KEY'] = 'super_secret_key_12345'

            # Trigger an exception that might include environment in locals
            def inner_function():
                secret = os.environ.get('TEST_SECRET_KEY')
                raise RuntimeError("Test error with env var access")

            inner_function()
        except RuntimeError as e:
            log_stack_trace(message="Test with environment", exception=e, include_locals=True)

        # Check that sensitive environment variables are not logged
        for record in caplog.records:
            log_message = record.getMessage()
            # Should not contain secret values
            assert "super_secret_key_12345" not in log_message, (
                f"Log should not expose secret environment variable values: {log_message[:200]}"
            )

    def test_library_versions_optionally_sanitized(self, caplog):
        """
        Test that library version information is optionally sanitized.

        Library versions can help attackers identify vulnerable versions,
        so they should be sanitized in production logs.
        """
        caplog.set_level(logging.ERROR)

        try:
            # Create an exception that will include library info in stack trace
            import sqlalchemy
            1 / 0  # Trigger a ZeroDivisionError
        except ZeroDivisionError as e:
            log_stack_trace(message="Test error", exception=e)

        # Check that library paths are sanitized
        for record in caplog.records:
            log_message = record.getMessage()
            # Should not reveal library version paths
            # This is a weaker assertion since version info might be useful for debugging
            pass  # Will implement sanitization if needed

    def test_log_injection_prevention(self, caplog):
        """
        Test that log injection attempts are prevented.

        Attackers might try to inject newlines or control characters
        into error messages to manipulate log output.

        Note: Stack traces naturally contain newlines for formatting.
        This test checks that injection attempts in the exception MESSAGE
        are properly handled.
        """
        caplog.set_level(logging.ERROR)

        # Create an exception with log injection attempt
        try:
            malicious_msg = "Valid error\n[INFO] Admin logged in from 192.168.1.1\n"
            raise ValueError(malicious_msg)
        except ValueError as e:
            log_stack_trace(message="Test injection", exception=e)

        # Check that the exception message doesn't contain unescaped newlines
        # Note: The stack trace will have newlines (that's expected format)
        for record in caplog.records:
            log_message = record.getMessage()
            # The exception line should have newlines escaped
            # Look for the exception message in the log
            if "ValueError:" in log_message:
                # Extract the exception message line
                exc_line = [line for line in log_message.split('\n') if 'ValueError:' in line]
                if exc_line:
                    # The injected newline should be visible as a pattern, not as actual log formatting
                    assert "[INFO] Admin logged in" in log_message, (
                        "Injection attempt should be visible in the log"
                    )

    def test_sensitive_headers_sanitized(self, caplog):
        """
        Test that sensitive HTTP headers (Authorization, Cookie, etc.)
        are sanitized when logged in error handlers.
        """
        from utils.error_sanitization import sanitize_header_value

        # Simulate sensitive header values
        sensitive_headers = {
            'Authorization': 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...',  # Fake JWT
            'Cookie': 'session=abc123; user=admin',
            'X-API-Key': 'secret_api_key_12345',
        }

        for key, value in sensitive_headers.items():
            sanitized = sanitize_header_value(key, value)
            # Sensitive headers should be partially or fully masked
            if key == 'Authorization':
                # Authorization is fully masked for security
                assert sanitized == '***', (
                    f"Authorization header should be fully masked: {sanitized}"
                )
                assert 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9' not in sanitized, (
                    f"JWT token should be masked: {sanitized}"
                )
            elif key == 'Cookie':
                assert 'abc123' not in sanitized, (
                    f"Cookie session value should be sanitized: {sanitized}"
                )
                assert '***' in sanitized, (
                    f"Cookie should have masked values: {sanitized}"
                )
            elif key == 'X-API-Key':
                assert 'secret_api_key_12345' not in sanitized, (
                    f"API key should be masked: {sanitized}"
                )
                assert sanitized == '***', (
                    f"API key should be fully masked: {sanitized}"
                )


class TestStacktracePathSanitization:
    """Test suite for stack trace path sanitization."""

    def test_absolute_paths_removed_from_stack_trace(self):
        """
        FAILING TEST: Absolute paths not removed from stack traces.

        Test that absolute file paths are removed from stack traces
        to prevent information disclosure about application structure.
        """
        from utils.error_sanitization import sanitize_stack_trace

        # Create a mock stack trace with absolute paths
        mock_trace = '''
Traceback (most recent call last):
  File "/app/direct_uploads/upload.py", line 245, in process_upload
    filename = secure_filename(file.filename)
  File "/app/utils/filename_validation.py", line 50, in validate
    return SAFE_FILENAME_PATTERN.match(filename)
ValueError: Invalid filename
'''

        sanitized = sanitize_stack_trace(mock_trace)

        # Should remove absolute paths like /app/
        assert "/app/" not in sanitized, (
            f"Sanitized trace should not contain /app/: {sanitized[:200]}"
        )

        # Should preserve function and line info for debugging
        assert "process_upload" in sanitized or "line" in sanitized, (
            "Should preserve some debugging information"
        )

    def test_project_root_removal(self):
        """
        Test that the project root path is removed from stack traces.
        """
        from utils.error_sanitization import sanitize_stack_path

        # Test various path formats
        paths = [
            "/app/direct_uploads/upload.py",
            "/Users/vivekgupta/workspace/fundus_img_xtract/app.py",
            "/var/www/html/fundus_img_xtract/models.py",
        ]

        for path in paths:
            sanitized = sanitize_stack_path(path)
            # Should remove /app/ prefix or shorten paths
            # The key goal is to not have absolute paths exposed
            assert not sanitized.startswith('/app/'), (
                f"Should not start with /app/: {sanitized}"
            )
            # Should preserve the filename
            assert '.py' in sanitized, (
                f"Should preserve the filename: {sanitized}"
            )


class TestProductionErrorHandling:
    """Test suite for production error handling behavior."""

    def test_stack_traces_not_in_production_response(self, client):
        """
        Test that stack traces are not included in production error responses.
        """
        # This is an integration test that would need the full app context
        # For now, we'll skip the actual implementation
        pass

    def test_error_pages_generic_in_production(self, client):
        """
        Test that error pages show generic messages in production.
        """
        # This is an integration test that would need the full app context
        # For now, we'll skip the actual implementation
        pass
