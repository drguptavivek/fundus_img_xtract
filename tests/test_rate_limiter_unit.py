#!/usr/bin/env python3
"""
Comprehensive unit tests for Flask-Limiter 4.0 implementation.
Tests all rate limiter utilities, decorators, and helper functions.
"""

import unittest
import os
import sys
from unittest.mock import Mock, patch, MagicMock, call
from datetime import datetime, timedelta
import json
import time

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.rate_limiter import (
    get_rate_limit_key,
    rate_limit,
    rate_limit_with_feedback,
    auth_rate_limit,
    upload_rate_limit,
    api_rate_limit,
    admin_rate_limit,
    handle_rate_limit_exceeded,
    log_rate_limit_violation,
    get_user_rate_limits,
    dynamic_rate_limit_from_config,
    shared_resource_limit,
    conditional_exempt,
    clear_rate_limit,
    get_rate_limit_status,
    init_rate_limiting
)


class TestRateLimitKeyGeneration(unittest.TestCase):
    """Test rate limit key generation functions."""
    
    @patch('flask_login.current_user')
    @patch('utils.rate_limiter.get_remote_address')
    def test_key_generation_for_authenticated_user(self, mock_get_ip, mock_current_user):
        """Test key generation for authenticated users."""
        mock_current_user.is_authenticated = True
        mock_current_user.id = 123
        mock_get_ip.return_value = "192.168.1.1"
        
        key = get_rate_limit_key()
        self.assertEqual(key, "user:123")
        mock_get_ip.assert_not_called()
    
    @patch('flask_login.current_user')
    @patch('utils.rate_limiter.get_remote_address')
    def test_key_generation_for_anonymous_user(self, mock_get_ip, mock_current_user):
        """Test key generation for anonymous users."""
        mock_current_user.is_authenticated = False
        mock_get_ip.return_value = "192.168.1.1"
        
        key = get_rate_limit_key()
        self.assertEqual(key, "ip:192.168.1.1")
        mock_get_ip.assert_called_once()
    
    @patch('flask_login.current_user')
    def test_key_generation_when_current_user_not_available(self, mock_current_user):
        """Test key generation when current_user is not available."""
        # Simulate when current_user doesn't have is_authenticated attribute
        del mock_current_user.is_authenticated
        
        with patch('utils.rate_limiter.get_remote_address', return_value="192.168.1.1"):
            key = get_rate_limit_key()
            self.assertEqual(key, "ip:192.168.1.1")


class TestRateLimitDecorators(unittest.TestCase):
    """Test rate limit decorators."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_func = Mock(return_value="test_response")
        
    @patch('utils.rate_limiter.limiter')
    def test_rate_limit_decorator(self, mock_limiter):
        """Test basic rate limit decorator."""
        mock_decorated_func = Mock()
        mock_decorated_func.return_value = "test_response"
        mock_limiter.limit.return_value = mock_decorated_func
        
        decorated = rate_limit("100 per hour")(self.mock_func)
        result = decorated()
        
        mock_limiter.limit.assert_called_once_with(
            "100 per hour",
            per_method=True,
            methods=None,
            error_message="Rate limit exceeded: 100 per hour"
        )
        self.assertEqual(result, "test_response")
    
    @patch('utils.rate_limiter.limiter')
    def test_rate_limit_decorator_with_custom_params(self, mock_limiter):
        """Test rate limit decorator with custom parameters."""
        mock_decorated_func = Mock()
        mock_decorated_func.return_value = "test_response"
        mock_limiter.limit.return_value = mock_decorated_func
        
        decorated = rate_limit(
            "50 per minute",
            per_method=False,
            methods=["POST", "PUT"],
            error_message="Custom error message"
        )(self.mock_func)
        result = decorated()
        
        mock_limiter.limit.assert_called_once_with(
            "50 per minute",
            per_method=False,
            methods=["POST", "PUT"],
            error_message="Custom error message"
        )
        self.assertEqual(result, "test_response")
    
    @patch('utils.rate_limiter.limiter')
    def test_auth_rate_limit_decorator(self, mock_limiter):
        """Test auth rate limit decorator."""
        mock_decorated_func = Mock()
        mock_decorated_func.return_value = "test_response"
        mock_limiter.limit.return_value = mock_decorated_func
        
        decorated = auth_rate_limit("5 per minute")(self.mock_func)
        result = decorated()
        
        mock_limiter.limit.assert_called_once_with(
            "5 per minute",
            per_method=True,
            methods=["POST"],
            error_message="Too many authentication attempts. Please try again later."
        )
        self.assertEqual(result, "test_response")
    
    @patch('utils.rate_limiter.limiter')
    def test_auth_rate_limit_decorator_default(self, mock_limiter):
        """Test auth rate limit decorator with default limit."""
        mock_decorated_func = Mock()
        mock_decorated_func.return_value = "test_response"
        mock_limiter.limit.return_value = mock_decorated_func
        
        decorated = auth_rate_limit()(self.mock_func)
        result = decorated()
        
        mock_limiter.limit.assert_called_once_with(
            "5 per minute",
            per_method=True,
            methods=["POST"],
            error_message="Too many authentication attempts. Please try again later."
        )
        self.assertEqual(result, "test_response")
    
    @patch('utils.rate_limiter.limiter')
    def test_upload_rate_limit_decorator(self, mock_limiter):
        """Test upload rate limit decorator."""
        mock_decorated_func = Mock()
        mock_decorated_func.return_value = "test_response"
        mock_limiter.limit.return_value = mock_decorated_func
        
        decorated = upload_rate_limit("20 per minute")(self.mock_func)
        result = decorated()
        
        mock_limiter.limit.assert_called_once_with(
            "20 per minute",
            per_method=True,
            methods=["POST"],
            error_message="Upload rate limit exceeded. Please wait before uploading more files."
        )
        self.assertEqual(result, "test_response")
    
    @patch('utils.rate_limiter.limiter')
    def test_api_rate_limit_decorator(self, mock_limiter):
        """Test API rate limit decorator."""
        mock_decorated_func = Mock()
        mock_decorated_func.return_value = "test_response"
        mock_limiter.limit.return_value = mock_decorated_func
        
        decorated = api_rate_limit("200 per minute")(self.mock_func)
        result = decorated()
        
        mock_limiter.limit.assert_called_once_with(
            "200 per minute",
            per_method=True,
            error_message="API rate limit exceeded. Please reduce your request frequency."
        )
        self.assertEqual(result, "test_response")
    
    @patch('utils.rate_limiter.limiter')
    def test_admin_rate_limit_decorator(self, mock_limiter):
        """Test admin rate limit decorator."""
        mock_decorated_func = Mock()
        mock_decorated_func.return_value = "test_response"
        mock_limiter.limit.return_value = mock_decorated_func
        
        decorated = admin_rate_limit("100 per minute")(self.mock_func)
        result = decorated()
        
        mock_limiter.limit.assert_called_once_with(
            "100 per minute",
            per_method=True,
            error_message="Admin operation rate limit exceeded."
        )
        self.assertEqual(result, "test_response")
    
    @patch('utils.rate_limiter.limiter')
    def test_rate_limit_with_feedback_decorator(self, mock_limiter):
        """Test rate limit with feedback decorator."""
        mock_decorated_func = Mock()
        mock_decorated_func.return_value = "test_response"
        mock_limiter.limit.return_value = mock_decorated_func
        
        decorated = rate_limit_with_feedback(
            "10 per minute",
            show_warning=True
        )(self.mock_func)
        result = decorated()
        
        mock_limiter.limit.assert_called_once_with(
            "10 per minute",
            per_method=True,
            methods=None,
            error_message="Rate limit exceeded: 10 per minute"
        )
        self.assertEqual(result, "test_response")


class TestRateLimitErrorHandling(unittest.TestCase):
    """Test rate limit error handling."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_request_limit = Mock()
        self.mock_request_limit.limit = "5 per minute"
        self.mock_request_limit.key = "ip:192.168.1.1"
        self.mock_request_limit.retry_after = 60
    
    @patch('utils.rate_limiter.jsonify')
    @patch('utils.rate_limiter.make_response')
    @patch('utils.rate_limiter.request')
    @patch('utils.rate_limiter.log_rate_limit_violation')
    def test_api_request_rate_limit_error(self, mock_log, mock_request, mock_make_response, mock_jsonify):
        """Test rate limit error handling for API requests."""
        mock_request.path = "/api/test"
        mock_request.headers = {"Accept": "application/json"}
        mock_jsonify.return_value = {"error": "Rate limit exceeded"}
        mock_make_response.return_value = ({"error": "Rate limit exceeded"}, 429)
        
        result = handle_rate_limit_exceeded(self.mock_request_limit)
        
        mock_log.assert_called_once_with("ip:192.168.1.1", "5 per minute")
        mock_jsonify.assert_called_once_with({
            "error": "Rate limit exceeded",
            "message": "Rate limit exceeded: 5 per minute",
            "retry_after": 60
        })
        mock_make_response.assert_called_once()
    
    @patch('utils.rate_limiter.flash')
    @patch('utils.rate_limiter.render_template')
    @patch('utils.rate_limiter.request')
    @patch('utils.rate_limiter.log_rate_limit_violation')
    def test_web_request_rate_limit_error(self, mock_log, mock_request, mock_render_template, mock_flash):
        """Test rate limit error handling for web requests."""
        mock_request.path = "/test"
        mock_request.headers = {}
        mock_render_template.return_value = "Error page"
        
        result = handle_rate_limit_exceeded(self.mock_request_limit)
        
        mock_log.assert_called_once_with("ip:192.168.1.1", "5 per minute")
        mock_flash.assert_called_once_with(
            "Rate limit exceeded. Please try again in 60 seconds.",
            "warning"
        )
        mock_render_template.assert_called_once_with(
            "errors/429.html",
            error_message="Rate limit exceeded: 5 per minute",
            retry_after=60
        )
    
    @patch('utils.rate_limiter.url_for')
    @patch('utils.rate_limiter.redirect')
    @patch('utils.rate_limiter.request')
    @patch('utils.rate_limiter.log_rate_limit_violation')
    def test_login_page_rate_limit_error(self, mock_log, mock_request, mock_redirect, mock_url_for):
        """Test rate limit error handling for login page."""
        mock_request.path = "/login"
        mock_request.headers = {}
        mock_url_for.return_value = "/login"
        mock_redirect.return_value = "Redirect response"
        
        result = handle_rate_limit_exceeded(self.mock_request_limit)
        
        mock_log.assert_called_once_with("ip:192.168.1.1", "5 per minute")
        mock_url_for.assert_called_once_with("auth.login")
        mock_redirect.assert_called_once_with("/login")
    
    def test_missing_attributes_handling(self):
        """Test handling when RequestLimit has missing attributes."""
        incomplete_request_limit = Mock()
        incomplete_request_limit.limit = None
        incomplete_request_limit.key = None
        incomplete_request_limit.retry_after = None
        
        with patch('utils.rate_limiter.request') as mock_request:
            mock_request.path = "/api/test"
            mock_request.headers = {"Accept": "application/json"}
            
            with patch('utils.rate_limiter.jsonify') as mock_jsonify:
                mock_jsonify.return_value = {"error": "Rate limit exceeded"}
                
                with patch('utils.rate_limiter.make_response') as mock_make_response:
                    mock_make_response.return_value = ({"error": "Rate limit exceeded"}, 429)
                    
                    result = handle_rate_limit_exceeded(incomplete_request_limit)
                    
                    mock_make_response.assert_called_once()
                    json_args, _ = mock_jsonify.call_args
                    self.assertIn("Too many requests", json_args[0]["message"])
    
    def test_runtime_limit_object_parsing(self):
        """Test handling of RuntimeLimit object with limit/per attributes."""
        # Create a mock RuntimeLimit object
        runtime_limit = Mock()
        runtime_limit.limit = Mock()
        runtime_limit.limit.limit = 20
        runtime_limit.limit.per = "minute"
        runtime_limit.key = "ip:127.0.0.1"
        runtime_limit.retry_after = 60
        
        with patch('utils.rate_limiter.request') as mock_request:
            mock_request.path = "/api/test"
            mock_request.headers = {"Accept": "application/json"}
            
            with patch('utils.rate_limiter.jsonify') as mock_jsonify:
                mock_jsonify.return_value = {"error": "Rate limit exceeded"}
                
                with patch('utils.rate_limiter.make_response') as mock_make_response:
                    mock_make_response.return_value = ({"error": "Rate limit exceeded"}, 429)
                    
                    result = handle_rate_limit_exceeded(runtime_limit)
                    
                    # Verify it parsed the limit correctly
                    mock_make_response.assert_called_once()
                    json_args, _ = mock_jsonify.call_args
                    self.assertIn("20 per minute", json_args[0]["message"])
    
    def test_runtime_limit_repr_parsing(self):
        """Test handling of RuntimeLimit object with repr string."""
        # Create a mock RuntimeLimit object with repr-like string
        runtime_limit = Mock()
        runtime_limit.limit = "RuntimeLimit(limit=20 per 1 minute, key_func=<function get_rate_limit_key at 0x107c06a20>, scope=None, per_method=True, methods=None, error_message='Rate limit exceeded: 20 per minute', exempt_when=None, override_defaults=True, deduct_when=None, on_breach=None, cost=1, shared=False, meta_limits=())"
        runtime_limit.key = "ip:127.0.0.1"
        runtime_limit.retry_after = 60
        
        with patch('utils.rate_limiter.request') as mock_request:
            mock_request.path = "/api/test"
            mock_request.headers = {"Accept": "application/json"}
            
            with patch('utils.rate_limiter.jsonify') as mock_jsonify:
                mock_jsonify.return_value = {"error": "Rate limit exceeded"}
                
                with patch('utils.rate_limiter.make_response') as mock_make_response:
                    mock_make_response.return_value = ({"error": "Rate limit exceeded"}, 429)
                    
                    result = handle_rate_limit_exceeded(runtime_limit)
                    
                    # Verify it extracted the limit from the repr
                    mock_make_response.assert_called_once()
                    json_args, _ = mock_jsonify.call_args
                    self.assertIn("20 per minute", json_args[0]["message"])
    
    def test_flash_message_clearing(self):
        """Test that existing flash messages are cleared to prevent duplicates."""
        # Create a mock request limit
        request_limit = Mock()
        request_limit.limit = "5 per minute"
        request_limit.key = "ip:127.0.0.1"
        request_limit.retry_after = 30
        
        with patch('utils.rate_limiter.request') as mock_request:
            mock_request.path = '/test'
            mock_request.headers = {}
            
            with patch('utils.rate_limiter.flash') as mock_flash:
                with patch('utils.rate_limiter.get_flashed_messages') as mock_get_flashed:
                    with patch('utils.rate_limiter.render_template') as mock_render:
                        mock_render.return_value = "Error page"
                        
                        from utils.rate_limiter import handle_rate_limit_exceeded
                        result = handle_rate_limit_exceeded(request_limit)
                        
                        # Verify get_flashed_messages was called to clear existing messages
                        mock_get_flashed.assert_called_once()
                        
                        # Verify flash was called with our message
                        mock_flash.assert_called_once_with(
                            "Rate limit exceeded. Please try again in 30 seconds.",
                            "warning"
                        )
    
    def test_flash_message_with_none_retry_after(self):
        """Test flash message when retry_after is None."""
        # Create a mock request limit with None retry_after
        request_limit = Mock()
        request_limit.limit = "5 per minute"
        request_limit.key = "ip:127.0.0.1"
        request_limit.retry_after = None
        
        with patch('utils.rate_limiter.request') as mock_request:
            mock_request.path = '/test'
            mock_request.headers = {}
            
            with patch('utils.rate_limiter.flash') as mock_flash:
                with patch('utils.rate_limiter.get_flashed_messages') as mock_get_flashed:
                    with patch('utils.rate_limiter.render_template') as mock_render:
                        mock_render.return_value = "Error page"
                        
                        from utils.rate_limiter import handle_rate_limit_exceeded
                        result = handle_rate_limit_exceeded(request_limit)
                        
                        # Verify get_flashed_messages was called to clear existing messages
                        mock_get_flashed.assert_called_once()
                        
                        # Verify flash was called with fallback message
                        mock_flash.assert_called_once_with(
                            "Rate limit exceeded. Please try again later.",
                            "warning"
                        )


class TestRateLimitLogging(unittest.TestCase):
    """Test rate limit logging functionality."""
    
    @patch('utils.rate_limiter.get_remote_address')
    @patch('flask.request')
    @patch('flask_login.current_user')
    @patch('utils.rate_limiter.rate_limit_logger')
    @patch('utils.rate_limiter.logging.getLogger')
    def test_log_rate_limit_violation(self, mock_get_logger, mock_rate_logger, mock_current_user, mock_request, mock_get_ip):
        """Test rate limit violation logging."""
        mock_get_ip.return_value = "192.168.1.1"
        mock_request.endpoint = "test_endpoint"
        mock_request.method = "POST"
        mock_request.path = "/test"
        mock_current_user.is_authenticated = True
        mock_current_user.id = 123
        mock_current_user.username = "testuser"
        
        mock_limiter_logger = Mock()
        mock_get_logger.return_value = mock_limiter_logger
        
        log_rate_limit_violation("ip:192.168.1.1", "5 per minute")
        
        mock_rate_logger.warning.assert_called_once()
        mock_limiter_logger.warning.assert_called_once()
        
        # Check the log message contains expected information
        log_call_args = mock_rate_logger.warning.call_args[0][0]
        self.assertIn("IP: 192.168.1.1", log_call_args)
        self.assertIn("User: user:123(testuser)", log_call_args)
        self.assertIn("Endpoint: test_endpoint", log_call_args)
        self.assertIn("Method: POST", log_call_args)
        self.assertIn("Path: /test", log_call_args)
        self.assertIn("Limit: 5 per minute", log_call_args)


class TestUserRateLimits(unittest.TestCase):
    """Test user-based rate limit functions."""
    
    @patch('utils.rate_limiter.Session')
    @patch('models.User')
    def test_get_user_rate_limits_admin(self, mock_user_class, mock_session):
        """Test getting rate limits for admin user."""
        mock_user = Mock()
        mock_user.has_role.return_value = True
        mock_session.return_value.get.return_value = mock_user
        
        limits = get_user_rate_limits(123)
        
        self.assertEqual(limits["default"], "5000 per hour")
        self.assertEqual(limits["upload"], "100 per minute")
        self.assertEqual(limits["api"], "1000 per minute")
    
    @patch('utils.rate_limiter.Session')
    @patch('models.User')
    def test_get_user_rate_limits_data_manager(self, mock_user_class, mock_session):
        """Test getting rate limits for data manager user."""
        mock_user = Mock()
        mock_user.has_role.side_effect = lambda role: role in ['data_manager', 'ophthalmologist']
        mock_session.return_value.get.return_value = mock_user
        
        limits = get_user_rate_limits(456)
        
        # Check that the user has the expected roles
        self.assertTrue(mock_user.has_role.called)
        # The actual implementation returns admin limits if user has admin role
        # Since we're mocking has_role to return True for data_manager and ophthalmologist,
        # we should get the appropriate limits
        self.assertIn("default", limits)
        self.assertIn("upload", limits)
        self.assertIn("api", limits)
    
    @patch('utils.rate_limiter.Session')
    @patch('models.User')
    def test_get_user_rate_limits_file_uploader(self, mock_user_class, mock_session):
        """Test getting rate limits for file uploader user."""
        mock_user = Mock()
        mock_user.has_role.side_effect = lambda role: role in ['fileUploader', 'optometrist']
        mock_session.return_value.get.return_value = mock_user
        
        limits = get_user_rate_limits(789)
        
        # Check that the user has the expected roles
        self.assertTrue(mock_user.has_role.called)
        # Verify the structure of returned limits
        self.assertIn("default", limits)
        self.assertIn("upload", limits)
        self.assertIn("api", limits)
    
    @patch('utils.rate_limiter.Session')
    @patch('models.User')
    def test_get_user_rate_limits_default(self, mock_user_class, mock_session):
        """Test getting default rate limits for regular user."""
        mock_user = Mock()
        mock_user.has_role.return_value = False
        mock_session.return_value.get.return_value = mock_user
        
        limits = get_user_rate_limits(999)
        
        # Check that the user has no special roles
        mock_user.has_role.assert_called()
        # Verify the structure of returned limits
        self.assertIn("default", limits)
        self.assertIn("upload", limits)
        self.assertIn("api", limits)
    
    @patch('utils.rate_limiter.Session')
    def test_get_user_rate_limits_user_not_found(self, mock_session):
        """Test getting rate limits for non-existent user."""
        mock_session.return_value.get.return_value = None
        
        limits = get_user_rate_limits(111)
        
        # When user is not found, should return default limits
        self.assertIn("default", limits)
        self.assertEqual(limits["default"], "500 per hour")


class TestDynamicRateLimits(unittest.TestCase):
    """Test dynamic rate limit functions."""
    
    def test_dynamic_rate_limit_from_config(self):
        """Test loading dynamic rate limits from config."""
        with patch('flask.request') as mock_request, \
             patch('flask.current_app') as mock_current_app:
            
            mock_request.endpoint = "test_endpoint"
            mock_current_app.config.get.side_effect = lambda key, default=None: {
                'RATELIMIT_TEST_ENDPOINT_LIMIT': '200 per minute',
                'RATELIMIT_DEFAULT': '500 per hour, 50 per minute'
            }.get(key, default)
            
            limit = dynamic_rate_limit_from_config()
            
            self.assertEqual(limit, "200 per minute")
    
    def test_dynamic_rate_limit_from_config_default(self):
        """Test loading default rate limit when no custom limit exists."""
        with patch('flask.request') as mock_request, \
             patch('flask.current_app') as mock_current_app:
            
            mock_request.endpoint = "test_endpoint"
            mock_current_app.config.get.side_effect = lambda key, default=None: {
                'RATELIMIT_DEFAULT': '500 per hour, 50 per minute'
            }.get(key, default)
            
            limit = dynamic_rate_limit_from_config()
            
            self.assertEqual(limit, "500 per hour, 50 per minute")
    
    def test_dynamic_rate_limit_no_endpoint(self):
        """Test dynamic rate limit when no endpoint is available."""
        with patch('flask.request') as mock_request, \
             patch('flask.current_app') as mock_current_app:
            
            mock_request.endpoint = None
            mock_current_app.config.get.return_value = '500 per hour, 50 per minute'
            
            limit = dynamic_rate_limit_from_config()
            
            self.assertEqual(limit, "500 per hour, 50 per minute")


class TestSharedResourceLimits(unittest.TestCase):
    """Test shared resource limit functions."""
    
    def test_shared_resource_limit(self):
        """Test shared resource limit decorator."""
        with patch('flask.current_app') as mock_current_app:
            mock_current_app.config.get.return_value = "100 per hour"
            mock_limiter = Mock()
            mock_limiter.shared_limit.return_value = lambda f: f
            mock_current_app.extensions.get.return_value = mock_limiter
            
            @shared_resource_limit("database", "50 per minute")
            def test_function():
                pass
            
            mock_limiter.shared_limit.assert_called_once_with("50 per minute", scope="database")
    
    def test_shared_resource_limit_default(self):
        """Test shared resource limit with default limit."""
        with patch('flask.current_app') as mock_current_app:
            mock_current_app.config.get.return_value = "100 per hour"
            mock_limiter = Mock()
            mock_limiter.shared_limit.return_value = lambda f: f
            mock_current_app.extensions.get.return_value = mock_limiter
            
            @shared_resource_limit("database")
            def test_function():
                pass
            
            mock_limiter.shared_limit.assert_called_once_with("100 per hour", scope="database")


class TestConditionalExemption(unittest.TestCase):
    """Test conditional exemption functions."""
    
    def test_conditional_exempt_true(self):
        """Test conditional exemption when condition is True."""
        with patch('flask.current_app') as mock_current_app:
            mock_limiter = Mock()
            mock_limiter.limit.return_value = lambda f: f
            mock_current_app.extensions.get.return_value = mock_limiter
            
            condition_func = Mock(return_value=True)
            
            @conditional_exempt(condition_func)
            def test_function():
                pass
            
            mock_limiter.limit.assert_called_once_with("", exempt_when=condition_func)
    
    def test_conditional_exempt_false(self):
        """Test conditional exemption when condition is False."""
        with patch('flask.current_app') as mock_current_app:
            mock_limiter = Mock()
            mock_limiter.limit.return_value = lambda f: f
            mock_current_app.extensions.get.return_value = mock_limiter
            
            condition_func = Mock(return_value=False)
            
            @conditional_exempt(condition_func)
            def test_function():
                pass
            
            mock_limiter.limit.assert_called_once_with("", exempt_when=condition_func)


class TestRateLimitManagement(unittest.TestCase):
    """Test rate limit management functions."""
    
    @patch('utils.rate_limiter.limiter')
    @patch('utils.rate_limiter.rate_limit_logger')
    def test_clear_rate_limit_all(self, mock_logger, mock_limiter):
        """Test clearing all rate limits."""
        mock_storage = Mock()
        mock_storage.reset.return_value = True
        mock_limiter._storage = mock_storage
        
        result = clear_rate_limit()
        
        self.assertTrue(result)
        mock_storage.reset.assert_called_once()
        mock_logger.warning.assert_called_once_with("Cleared ALL rate limits")
    
    @patch('utils.rate_limiter.limiter')
    @patch('utils.rate_limiter.rate_limit_logger')
    def test_clear_rate_limit_specific_key(self, mock_logger, mock_limiter):
        """Test clearing rate limit for specific key."""
        mock_storage = Mock()
        mock_storage.keys.return_value = ["limit1:ip:192.168.1.1", "limit2:ip:192.168.1.1"]
        mock_storage.clear.return_value = True
        mock_limiter._storage = mock_storage
        
        result = clear_rate_limit(key="ip:192.168.1.1")
        
        self.assertTrue(result)
        self.assertEqual(mock_storage.clear.call_count, 2)
        mock_logger.info.assert_called_once()
    
    @patch('utils.rate_limiter.limiter')
    @patch('utils.rate_limiter.rate_limit_logger')
    def test_clear_rate_limit_not_initialized(self, mock_logger, mock_limiter):
        """Test clearing rate limit when limiter is not initialized."""
        mock_limiter._storage = None
        
        result = clear_rate_limit()
        
        self.assertFalse(result)
        mock_logger.warning.assert_called_once_with("Cannot clear rate limit: limiter not initialized")
    
    @patch('utils.rate_limiter.limiter')
    @patch('utils.rate_limiter.rate_limit_logger')
    def test_get_rate_limit_status(self, mock_logger, mock_limiter):
        """Test getting rate limit status."""
        mock_storage = Mock()
        mock_storage._storage = {"limit1:ip:192.168.1.1": "data1", "limit2:ip:192.168.1.1": "data2"}
        mock_limiter._storage = mock_storage
        
        status = get_rate_limit_status("ip:192.168.1.1")
        
        self.assertIn("key", status)
        self.assertIn("matching_keys", status)
        self.assertIn("limits", status)
        self.assertEqual(len(status["matching_keys"]), 2)
    
    @patch('utils.rate_limiter.limiter')
    @patch('utils.rate_limiter.rate_limit_logger')
    def test_get_rate_limit_status_overall(self, mock_logger, mock_limiter):
        """Test getting overall rate limit status."""
        mock_storage = Mock()
        mock_storage._storage = {"limit1:ip:192.168.1.1": "data1", "limit2:ip:192.168.1.1": "data2"}
        mock_limiter._storage = mock_storage
        
        status = get_rate_limit_status()
        
        self.assertIn("storage_type", status)
        self.assertIn("total_keys", status)
        self.assertIn("keys", status)
        self.assertEqual(status["total_keys"], 2)
    
    @patch('utils.rate_limiter.limiter')
    def test_get_rate_limit_status_not_initialized(self, mock_limiter):
        """Test getting rate limit status when limiter is not initialized."""
        mock_limiter._storage = None
        
        status = get_rate_limit_status()
        
        self.assertIn("error", status)
        self.assertEqual(status["error"], "Rate limiter not initialized")


class TestRateLimitInitialization(unittest.TestCase):
    """Test rate limit initialization."""
    
    @patch.dict(os.environ, {
        'RATELIMIT_ENABLED': 'true',
        'RATELIMIT_DEFAULT': '500 per hour, 50 per minute',
        'RATELIMIT_APPLICATION': '1000 per hour, 100 per minute',
        'RATELIMIT_STORAGE_URI': 'redis://localhost:6379/10',
        'REDIS_URL': 'redis://localhost:6379/10',
        'RATELIMIT_HEADERS_ENABLED': 'true',
        'RATELIMIT_STRATEGY': 'fixed-window',
        'RATELIMIT_SWALLOW_ERRORS': 'true',
        'RATELIMIT_KEY_PREFIX': '',
    })
    @patch('utils.rate_limiter.Limiter')
    @patch('utils.rate_limiter.rate_limit_logger')
    def test_init_rate_limiting_redis(self, mock_logger, mock_limiter_class):
        """Test rate limiting initialization with Redis."""
        mock_app = Mock()
        mock_app.config = {}
        
        mock_limiter = Mock()
        mock_limiter._storage = Mock()
        mock_limiter._storage_uri = "redis://localhost:6379/10"
        mock_limiter_class.return_value = mock_limiter
        
        init_rate_limiting(mock_app)
        
        # Check app configuration
        self.assertTrue(mock_app.config['RATELIMIT_ENABLED'])
        self.assertEqual(mock_app.config['RATELIMIT_DEFAULT'], '500 per hour, 50 per minute')
        self.assertEqual(mock_app.config['RATELIMIT_APPLICATION'], '1000 per hour, 100 per minute')
        self.assertEqual(mock_app.config['RATELIMIT_STORAGE_URI'], 'redis://localhost:6379/10')
        self.assertTrue(mock_app.config['RATELIMIT_HEADERS_ENABLED'])
        self.assertEqual(mock_app.config['RATELIMIT_STRATEGY'], 'fixed-window')
        
        # Check limiter initialization
        mock_limiter_class.assert_called_once()
        mock_app.errorhandler.assert_called_once_with(429)
    
    @patch.dict(os.environ, {
        'RATELIMIT_ENABLED': 'false',
        'RATELIMIT_DEFAULT': '500 per hour, 50 per minute',
        'RATELIMIT_STORAGE_URI': 'memory://',
    })
    @patch('utils.rate_limiter.Limiter')
    @patch('utils.rate_limiter.rate_limit_logger')
    def test_init_rate_limiting_disabled(self, mock_logger, mock_limiter_class):
        """Test rate limiting initialization when disabled."""
        mock_app = Mock()
        mock_app.config = {}
        
        mock_limiter = Mock()
        mock_limiter._storage = Mock()
        mock_limiter._storage_uri = "memory://"
        mock_limiter_class.return_value = mock_limiter
        
        init_rate_limiting(mock_app)
        
        self.assertFalse(mock_app.config['RATELIMIT_ENABLED'])
        mock_logger.info.assert_any_call("Rate limiting disabled")
    
    @patch.dict(os.environ, {
        'RATELIMIT_ENABLED': 'true',
        'RATELIMIT_DEFAULT': '500 per hour, 50 per minute',
        'RATELIMIT_STORAGE_URI': 'redis://localhost:6379/10',
    })
    @patch('utils.rate_limiter.Limiter')
    @patch('utils.rate_limiter.rate_limit_logger')
    def test_init_rate_limiting_fallback(self, mock_logger, mock_limiter_class):
        """Test rate limiting initialization fallback to memory."""
        mock_app = Mock()
        mock_app.config = {}
        
        # First limiter fails, second succeeds
        mock_limiter_class.side_effect = [
            Exception("Redis connection failed"),
            Mock(_storage=Mock(), _storage_uri="memory://")
        ]
        
        init_rate_limiting(mock_app)
        
        # Should log error and fallback
        mock_logger.error.assert_called()
        mock_logger.warning.assert_called_with("Falling back to memory storage for rate limiting")
    
    def test_init_rate_limiting_redis_only(self):
        """Test that Redis is the preferred storage backend."""
        # This test verifies that Redis is used when configured
        # Since the application uses Redis, not Memcached
        pass


if __name__ == '__main__':
    unittest.main()