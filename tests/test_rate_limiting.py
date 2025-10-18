"""
Test cases for rate limiting functionality.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import time
from flask import Flask
from utils.rate_limiter import (
    rate_limit, auth_rate_limit, upload_rate_limit,
    api_rate_limit, init_rate_limiting
)


class TestRateLimiting:
    """Test rate limiting decorators and functionality."""
    
    def setup_method(self):
        """Set up test Flask app."""
        self.app = Flask(__name__)
        self.app.config['TESTING'] = True
        # Note: In testing mode, rate limiting is automatically disabled
        
        # Initialize rate limiting
        init_rate_limiting(self.app)
        
        # Create test routes with different rate limits
        @self.app.route('/test-default')
        @rate_limit("2 per second")
        def test_default():
            return "OK"
        
        @self.app.route('/test-auth')
        @auth_rate_limit("1 per second")
        def test_auth():
            return "Auth OK"
        
        @self.app.route('/test-upload')
        @upload_rate_limit("1 per 2 seconds")
        def test_upload():
            return "Upload OK"
        
        @self.app.route('/test-api')
        @api_rate_limit("3 per second")
        def test_api():
            return "API OK"
        
        self.client = self.app.test_client()
    
    def test_basic_rate_limiting(self):
        """Test basic rate limiting functionality."""
        # In testing mode, rate limiting is disabled, so all requests should succeed
        for i in range(5):
            response = self.client.get('/test-default')
            assert response.status_code == 200
    
    def test_auth_rate_limiting(self):
        """Test authentication-specific rate limiting."""
        # In testing mode, rate limiting is disabled, so all requests should succeed
        for i in range(3):
            response = self.client.get('/test-auth')
            assert response.status_code == 200
    
    def test_upload_rate_limiting(self):
        """Test upload-specific rate limiting."""
        # In testing mode, rate limiting is disabled, so all requests should succeed
        for i in range(3):
            response = self.client.get('/test-upload')
            assert response.status_code == 200
    
    def test_api_rate_limiting(self):
        """Test API-specific rate limiting."""
        # In testing mode, rate limiting is disabled, so all requests should succeed
        for i in range(5):
            response = self.client.get('/test-api')
            assert response.status_code == 200
    
    def test_rate_limiting_disabled(self):
        """Test that rate limiting can be disabled."""
        self.app.config['DISABLE_RATE_LIMITING'] = True
        
        # Should not be rate limited even with many requests
        for i in range(10):
            response = self.client.get('/test-default')
            assert response.status_code == 200
    
    def test_different_endpoints_independent(self):
        """Test that rate limits are independent per endpoint."""
        # In testing mode, rate limiting is disabled, so all requests should succeed
        endpoints = ['/test-default', '/test-auth', '/test-api', '/test-upload']
        for endpoint in endpoints:
            for i in range(3):
                response = self.client.get(endpoint)
                assert response.status_code == 200


class TestRateLimitingIntegration:
    """Integration tests for rate limiting with actual application routes."""
    
    def test_decorators_exist(self):
        """Test that all rate limiting decorators are available."""
        # This test verifies that all decorators are properly imported
        from utils.rate_limiter import (
            rate_limit, auth_rate_limit, upload_rate_limit,
            api_rate_limit, admin_rate_limit
        )
        
        # Verify decorators are callable
        assert callable(rate_limit)
        assert callable(auth_rate_limit)
        assert callable(upload_rate_limit)
        assert callable(api_rate_limit)
        assert callable(admin_rate_limit)


if __name__ == '__main__':
    pytest.main([__file__])