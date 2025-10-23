#!/usr/bin/env python3
"""
Unit test for the rate limiter fix to verify RequestLimit object handling.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

from utils.rate_limiter import handle_rate_limit_exceeded

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestRateLimiterFix(unittest.TestCase):
    """Test cases for the rate limiter fix."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Create a mock RequestLimit object
        self.mock_request_limit = Mock()
        self.mock_request_limit.limit = "5 per minute"
        self.mock_request_limit.key = "ip:127.0.0.1"
        self.mock_request_limit.retry_after = 60
    
    @patch('flask.make_response')
    @patch('flask.jsonify')
    @patch('flask.request')
    def test_api_request_rate_limit(self, mock_request, mock_jsonify, mock_make_response):
        """Test rate limit handling for API requests."""
        # Configure mock request for API endpoint
        mock_request.path = '/api/test'
        mock_request.headers = {'Accept': 'application/json'}
        
        # Configure mock responses
        mock_jsonify.return_value = {"error": "Rate limit exceeded"}
        mock_make_response.return_value = ({"error": "Rate limit exceeded"}, 429)
        
        # Call the handler
        from utils.rate_limiter import handle_rate_limit_exceeded
        result = handle_rate_limit_exceeded(self.mock_request_limit)
        
        # Verify the response
        mock_make_response.assert_called_once()
        args, kwargs = mock_make_response.call_args
        
        # Check that jsonify was called with correct error message
        mock_jsonify.assert_called_once()
        json_args, json_kwargs = mock_jsonify.call_args
        self.assertEqual(json_args[0]["error"], "Rate limit exceeded")
        self.assertIn("Rate limit exceeded: 5 per minute", json_args[0]["message"])
        self.assertEqual(json_args[0]["retry_after"], 60)
    
    @patch('flask.render_template')
    @patch('flask.flash')
    @patch('flask.request')
    def test_web_request_rate_limit(self, mock_request, mock_flash, mock_render_template):
        """Test rate limit handling for web requests."""
        # Configure mock request for web endpoint
        mock_request.path = '/test'
        mock_request.headers = {}
        
        # Configure mock render_template response
        mock_render_template.return_value = "HTML Error Page"
        
        # Call the handler
        from utils.rate_limiter import handle_rate_limit_exceeded
        result = handle_rate_limit_exceeded(self.mock_request_limit)
        
        # Verify flash message was added
        mock_flash.assert_called_once_with(
            "Rate limit exceeded. Please try again in 60 seconds.",
            "warning"
        )
        
        # Verify render_template was called with correct arguments
        mock_render_template.assert_called_once_with(
            "errors/429.html",
            error_message="Rate limit exceeded: 5 per minute",
            retry_after=60
        )
    
    @patch('flask.url_for')
    @patch('flask.redirect')
    @patch('flask.request')
    def test_login_page_rate_limit(self, mock_request, mock_redirect, mock_url_for):
        """Test rate limit handling for login page."""
        # Configure mock request for login page
        mock_request.path = '/login'
        mock_request.headers = {}
        
        # Configure mock url_for and redirect
        mock_url_for.return_value = '/login'
        mock_redirect.return_value = "Redirect Response"
        
        # Call the handler
        from utils.rate_limiter import handle_rate_limit_exceeded
        result = handle_rate_limit_exceeded(self.mock_request_limit)
        
        # Verify redirect to login page
        mock_url_for.assert_called_once_with('auth.login')
        mock_redirect.assert_called_once_with('/login')
    
    def test_missing_attributes(self):
        """Test handling when RequestLimit has missing attributes."""
        # Create a mock with missing attributes
        incomplete_request_limit = Mock()
        incomplete_request_limit.limit = None
        incomplete_request_limit.key = None
        incomplete_request_limit.retry_after = None
        
        # This should not raise an exception
        with patch('flask.request') as mock_request:
            mock_request.path = '/api/test'
            mock_request.headers = {'Accept': 'application/json'}
            
            with patch('flask.jsonify') as mock_jsonify:
                mock_jsonify.return_value = {"error": "Rate limit exceeded"}
                
                with patch('flask.make_response') as mock_make_response:
                    mock_make_response.return_value = ({"error": "Rate limit exceeded"}, 429)
                    
                    # This should not raise an AttributeError
                    from utils.rate_limiter import handle_rate_limit_exceeded
                    result = handle_rate_limit_exceeded(incomplete_request_limit)
                    
                    # Verify it handled the missing attributes gracefully
                    mock_make_response.assert_called_once()
                    json_args, _ = mock_jsonify.call_args
                    self.assertIn("unknown limit", json_args[0]["message"])


if __name__ == '__main__':
    unittest.main()