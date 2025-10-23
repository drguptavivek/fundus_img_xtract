#!/usr/bin/env python3
"""
Comprehensive integration tests for Flask-Limiter 4.0 implementation.
Tests rate limiting with real Flask app context and different backends.
"""

import pytest
import time
import os
import json
from unittest.mock import Mock, patch
from flask import request, g, session, jsonify
from utils.rate_limiter import (
    handle_rate_limit_exceeded,
    get_rate_limit_key,
    rate_limit,
    auth_rate_limit,
    upload_rate_limit,
    api_rate_limit,
    admin_rate_limit,
    clear_rate_limit,
    get_rate_limit_status,
    limiter
)


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


class TestRateLimitKeyGenerationIntegration:
    """Test rate limit key generation with Flask context."""
    
    def test_key_generation_with_anonymous_user(self, app):
        """Test key generation for anonymous users."""
        with app.test_request_context('/test', headers={'X-Forwarded-For': '192.168.1.100'}):
            key = get_rate_limit_key()
            assert key.startswith("ip:")
            assert "192.168.1.100" in key or "127.0.0.1" in key
    
    def test_key_generation_with_authenticated_user(self, app, test_users):
        """Test key generation for authenticated users."""
        with app.test_request_context('/test'):
            # Mock the current_user
            with patch('utils.rate_limiter.current_user') as mock_current_user:
                mock_current_user.is_authenticated = True
                mock_current_user.id = test_users["admin"].id
                
                key = get_rate_limit_key()
                assert key == f"user:{test_users['admin'].id}"


class TestRateLimitDecoratorIntegration:
    """Test rate limit decorators with Flask app."""
    
    def test_basic_rate_limit_decorator(self, app):
        """Test basic rate limit decorator functionality."""
        @app.route('/test-rate-limit')
        @rate_limit("10 per minute")
        def test_route():
            return jsonify({"message": "success"})
        
        with app.test_client() as client:
            # Make multiple requests to test rate limiting
            responses = []
            for i in range(15):
                response = client.get('/test-rate-limit')
                responses.append(response)
                if response.status_code == 429:
                    break
            
            # Should get at least some successful responses
            assert any(r.status_code == 200 for r in responses)
            # Should eventually get rate limited
            assert any(r.status_code == 429 for r in responses)
    
    def test_auth_rate_limit_decorator(self, app):
        """Test auth rate limit decorator."""
        @app.route('/test-auth-rate-limit', methods=['POST'])
        @auth_rate_limit("3 per minute")
        def test_auth_route():
            return jsonify({"message": "auth success"})
        
        with app.test_client() as client:
            # Make multiple POST requests
            responses = []
            for i in range(5):
                response = client.post('/test-auth-rate-limit')
                responses.append(response)
                if response.status_code == 429:
                    break
            
            # Should get at least some successful responses
            assert any(r.status_code == 200 for r in responses)
            # Should eventually get rate limited
            assert any(r.status_code == 429 for r in responses)
    
    def test_upload_rate_limit_decorator(self, app):
        """Test upload rate limit decorator."""
        @app.route('/test-upload-rate-limit', methods=['POST'])
        @upload_rate_limit("5 per minute")
        def test_upload_route():
            return jsonify({"message": "upload success"})
        
        with app.test_client() as client:
            # Make multiple POST requests
            responses = []
            for i in range(7):
                response = client.post('/test-upload-rate-limit')
                responses.append(response)
                if response.status_code == 429:
                    break
            
            # Should get at least some successful responses
            assert any(r.status_code == 200 for r in responses)
            # Should eventually get rate limited
            assert any(r.status_code == 429 for r in responses)
    
    def test_api_rate_limit_decorator(self, app):
        """Test API rate limit decorator."""
        @app.route('/api/test-api-rate-limit')
        @api_rate_limit("8 per minute")
        def test_api_route():
            return jsonify({"message": "api success"})
        
        with app.test_client() as client:
            # Make multiple requests
            responses = []
            for i in range(10):
                response = client.get('/api/test-api-rate-limit')
                responses.append(response)
                if response.status_code == 429:
                    break
            
            # Should get at least some successful responses
            assert any(r.status_code == 200 for r in responses)
            # Should eventually get rate limited
            assert any(r.status_code == 429 for r in responses)
    
    def test_admin_rate_limit_decorator(self, app):
        """Test admin rate limit decorator."""
        @app.route('/test-admin-rate-limit')
        @admin_rate_limit("6 per minute")
        def test_admin_route():
            return jsonify({"message": "admin success"})
        
        with app.test_client() as client:
            # Make multiple requests
            responses = []
            for i in range(8):
                response = client.get('/test-admin-rate-limit')
                responses.append(response)
                if response.status_code == 429:
                    break
            
            # Should get at least some successful responses
            assert any(r.status_code == 200 for r in responses)
            # Should eventually get rate limited
            assert any(r.status_code == 429 for r in responses)


class TestRateLimitHeadersIntegration:
    """Test rate limit headers in responses."""
    
    def test_rate_limit_headers_in_response(self, app):
        """Test that rate limit headers are included in responses."""
        @app.route('/test-headers')
        @rate_limit("5 per minute")
        def test_headers_route():
            return jsonify({"message": "success"})
        
        with app.test_client() as client:
            response = client.get('/test-headers')
            
            # Check for rate limit headers (if enabled)
            # Note: This depends on the configuration in app.py
            if app.config.get('RATELIMIT_HEADERS_ENABLED', False):
                assert 'X-RateLimit-Limit' in response.headers
                assert 'X-RateLimit-Remaining' in response.headers
    
    def test_rate_limit_headers_after_limit_exceeded(self, app):
        """Test rate limit headers after limit is exceeded."""
        @app.route('/test-headers-exceeded')
        @rate_limit("2 per minute")
        def test_headers_exceeded_route():
            return jsonify({"message": "success"})
        
        with app.test_client() as client:
            # Make requests until rate limited
            for i in range(4):
                response = client.get('/test-headers-exceeded')
                if response.status_code == 429:
                    # Check for retry-after header
                    assert 'retry-after' in response.headers or 'Retry-After' in response.headers
                    break


class TestRateLimitStorageBackends:
    """Test rate limiting with different storage backends."""
    
    @patch.dict(os.environ, {
        'RATELIMIT_STORAGE_URI': 'memory://',
        'RATELIMIT_ENABLED': 'true'
    })
    def test_memory_storage_backend(self, app_factory):
        """Test rate limiting with memory storage backend."""
        app = app_factory()
        
        @app.route('/test-memory')
        @rate_limit("3 per minute")
        def test_memory_route():
            return jsonify({"message": "memory success"})
        
        with app.test_client() as client:
            # Make multiple requests
            responses = []
            for i in range(5):
                response = client.get('/test-memory')
                responses.append(response)
                if response.status_code == 429:
                    break
            
            # Should work with memory storage
            assert any(r.status_code == 200 for r in responses)
            assert any(r.status_code == 429 for r in responses)
    
    @pytest.mark.skipif(
        not os.getenv('REDIS_URL') or not os.getenv('REDIS_URL').startswith('redis://'),
        reason="Redis not available"
    )
    @patch.dict(os.environ, {
        'RATELIMIT_STORAGE_URI': 'redis://localhost:6379/1',
        'REDIS_URL': 'redis://localhost:6379/1',
        'RATELIMIT_ENABLED': 'true'
    })
    def test_redis_storage_backend(self, app_factory):
        """Test rate limiting with Redis storage backend."""
        app = app_factory()
        
        @app.route('/test-redis')
        @rate_limit("3 per minute")
        def test_redis_route():
            return jsonify({"message": "redis success"})
        
        with app.test_client() as client:
            # Make multiple requests
            responses = []
            for i in range(5):
                response = client.get('/test-redis')
                responses.append(response)
                if response.status_code == 429:
                    break
            
            # Should work with Redis storage
            assert any(r.status_code == 200 for r in responses)
            assert any(r.status_code == 429 for r in responses)


class TestRateLimitManagementIntegration:
    """Test rate limit management functions."""
    
    def test_clear_rate_limit_integration(self, app):
        """Test clearing rate limits in integration context."""
        with app.app_context():
            # This test depends on the limiter being initialized
            if limiter and limiter._storage:
                # Try to clear a specific key
                result = clear_rate_limit(key="ip:127.0.0.1")
                # Result depends on storage backend
                assert isinstance(result, bool)
    
    def test_get_rate_limit_status_integration(self, app):
        """Test getting rate limit status in integration context."""
        with app.app_context():
            # This test depends on the limiter being initialized
            if limiter and limiter._storage:
                # Try to get status for a specific key
                status = get_rate_limit_status("ip:127.0.0.1")
                assert isinstance(status, dict)
                
                # Try to get overall status
                overall_status = get_rate_limit_status()
                assert isinstance(overall_status, dict)


class TestRateLimitWithAuthentication:
    """Test rate limiting with authenticated users."""
    
    def test_rate_limit_with_authenticated_user(self, app, test_users):
        """Test rate limiting behavior with authenticated users."""
        @app.route('/test-authenticated')
        @rate_limit("5 per minute")
        def test_authenticated_route():
            return jsonify({"message": "authenticated success"})
        
        with app.test_client(user=test_users["admin"]) as client:
            # Make multiple requests as authenticated user
            responses = []
            for i in range(7):
                response = client.get('/test-authenticated')
                responses.append(response)
                if response.status_code == 429:
                    break
            
            # Should get at least some successful responses
            assert any(r.status_code == 200 for r in responses)
            # Should eventually get rate limited
            assert any(r.status_code == 429 for r in responses)
    
    def test_rate_limit_with_different_users(self, app, test_users):
        """Test that different users have separate rate limits."""
        @app.route('/test-different-users')
        @rate_limit("3 per minute")
        def test_different_users_route():
            return jsonify({"message": "user success"})
        
        # Test with admin user
        with app.test_client(user=test_users["admin"]) as client:
            admin_responses = []
            for i in range(5):
                response = client.get('/test-different-users')
                admin_responses.append(response)
                if response.status_code == 429:
                    break
        
        # Test with resident user
        with app.test_client(user=test_users["resident"]) as client:
            resident_responses = []
            for i in range(5):
                response = client.get('/test-different-users')
                resident_responses.append(response)
                if response.status_code == 429:
                    break
        
        # Both users should have separate rate limits
        assert any(r.status_code == 200 for r in admin_responses)
        assert any(r.status_code == 200 for r in resident_responses)


class TestRateLimitErrorHandlingIntegration:
    """Test error handling in rate limiting."""
    
    def test_rate_limit_error_response_format(self, app):
        """Test the format of rate limit error responses."""
        @app.route('/test-error-format')
        @rate_limit("1 per minute")
        def test_error_format_route():
            return jsonify({"message": "success"})
        
        with app.test_client() as client:
            # Make first request (should succeed)
            response1 = client.get('/test-error-format')
            assert response1.status_code == 200
            
            # Make second request (should be rate limited)
            response2 = client.get('/test-error-format')
            assert response2.status_code == 429
            
            # Check response format for API
            if request.path.startswith('/api/') or request.headers.get('Accept') == 'application/json':
                data = response2.get_json()
                assert data is not None
                assert 'error' in data
                assert 'message' in data
                assert 'retry_after' in data
    
    def test_rate_limit_with_custom_error_message(self, app):
        """Test rate limiting with custom error messages."""
        @app.route('/test-custom-error')
        @rate_limit("1 per minute", error_message="Custom rate limit message")
        def test_custom_error_route():
            return jsonify({"message": "success"})
        
        with app.test_client() as client:
            # Make first request (should succeed)
            client.get('/test-custom-error')
            
            # Make second request (should be rate limited with custom message)
            response = client.get('/test-custom-error')
            assert response.status_code == 429
            
            # Check if custom message is present
            data = response.get_json()
            if data:
                assert 'Custom rate limit message' in data.get('message', '')


class TestRateLimitPerformanceIntegration:
    """Test performance aspects of rate limiting."""
    
    def test_rate_limit_performance_impact(self, app):
        """Test that rate limiting doesn't significantly impact performance."""
        @app.route('/test-performance')
        @rate_limit("100 per minute")
        def test_performance_route():
            return jsonify({"message": "success"})
        
        with app.test_client() as client:
            # Measure time for multiple requests
            start_time = time.time()
            
            for i in range(10):
                response = client.get('/test-performance')
                assert response.status_code == 200
            
            end_time = time.time()
            total_time = end_time - start_time
            
            # Should complete within reasonable time (adjust threshold as needed)
            assert total_time < 2.0, f"Rate limiting took too long: {total_time}s"
    
    def test_rate_limit_concurrent_requests(self, app):
        """Test rate limiting with concurrent requests."""
        @app.route('/test-concurrent')
        @rate_limit("10 per minute")
        def test_concurrent_route():
            return jsonify({"message": "success"})
        
        with app.test_client() as client:
            # Make multiple requests quickly
            import threading
            import queue
            
            results = queue.Queue()
            
            def make_request():
                response = client.get('/test-concurrent')
                results.put(response.status_code)
            
            # Start multiple threads
            threads = []
            for i in range(15):
                thread = threading.Thread(target=make_request)
                threads.append(thread)
                thread.start()
            
            # Wait for all threads to complete
            for thread in threads:
                thread.join()
            
            # Check results
            success_count = 0
            rate_limited_count = 0
            
            while not results.empty():
                status = results.get()
                if status == 200:
                    success_count += 1
                elif status == 429:
                    rate_limited_count += 1
            
            # Should have some successful and some rate limited requests
            assert success_count > 0
            assert rate_limited_count > 0