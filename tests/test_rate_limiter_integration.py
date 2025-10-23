#!/usr/bin/env python3
"""
Integration test for the rate limiter fix to verify RequestLimit object handling.
This test runs with a real Flask app context.
"""

from unittest.mock import Mock
import pytest
from flask import request
from utils.rate_limiter import handle_rate_limit_exceeded


class TestRateLimiterIntegration:
    """Integration tests for the rate limiter fix."""
    
    @pytest.fixture(autouse=True)
    def setup_request_limit_mock(self):
        """Set up a mock RequestLimit object for all tests."""
        self.mock_request_limit = Mock()
        self.mock_request_limit.limit = "5 per minute"
        self.mock_request_limit.key = "ip:127.0.0.1"
        self.mock_request_limit.retry_after = 60
    
    def test_request_limit_handling_with_api_endpoint(self, app):
        """Test that the handle_rate_limit_exceeded function works with API endpoints."""
        with app.test_request_context('/api/test', headers={'Accept': 'application/json'}):
            # This should not raise an AttributeError about 'description'
            result = handle_rate_limit_exceeded(self.mock_request_limit)
            
            # Verify it returns a response with status code 429
            assert result is not None
            # The result might be a Response object or a tuple
            if hasattr(result, 'status_code'):
                assert result.status_code == 429
            else:
                assert result[1] == 429  # Status code should be 429
    
    def test_request_limit_with_missing_attributes(self, app):
        """Test handling when RequestLimit has missing attributes."""
        with app.test_request_context('/api/test', headers={'Accept': 'application/json'}):
            # Create a mock with None attributes
            incomplete_request_limit = Mock()
            incomplete_request_limit.limit = None
            incomplete_request_limit.key = None
            incomplete_request_limit.retry_after = None
            
            # This should not raise an exception
            result = handle_rate_limit_exceeded(incomplete_request_limit)
            
            # Verify it handled the missing attributes gracefully
            assert result is not None
            if hasattr(result, 'status_code'):
                assert result.status_code == 429
            else:
                assert result[1] == 429
    
    def test_request_limit_with_web_endpoint(self, app):
        """Test rate limit handling for web endpoints."""
        with app.test_request_context('/test'):
            # This should not raise an AttributeError
            result = handle_rate_limit_exceeded(self.mock_request_limit)
            
            # Verify it returns a response
            assert result is not None
            if hasattr(result, 'status_code'):
                assert result.status_code == 429
            else:
                assert result[1] == 429
    
    def test_request_limit_with_login_endpoint(self, app):
        """Test rate limit handling for login endpoint."""
        with app.test_request_context('/login'):
            # This should not raise an AttributeError
            result = handle_rate_limit_exceeded(self.mock_request_limit)
            
            # Verify it returns a response
            assert result is not None
            if hasattr(result, 'status_code'):
                # Login endpoint returns a redirect (302) when rate limited
                assert result.status_code in [302, 429]
            else:
                assert result[1] in [302, 429]