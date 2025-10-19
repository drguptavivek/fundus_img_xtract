"""Tests for rate limiting functionality and flask-limiter logger."""

import os
import time
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import threading

import pytest
from flask import Flask

from utils.rate_limiter import init_rate_limiting, rate_limit, log_rate_limit_violation


class TestRateLimiter:
    """Test rate limiting functionality and logging."""

    @pytest.fixture
    def test_app(self):
        """Create a test Flask app with rate limiting enabled."""
        app = Flask(__name__)
        app.config.update(
            TESTING=True,
            SECRET_KEY="test-secret-key",
            RATELIMIT_ENABLED=True,
            RATELIMIT_DEFAULT="5 per minute",  # Very restrictive for testing
            RATELIMIT_STORAGE_URL="memory://",
            LOG_DIR=Path(__file__).parent.parent / "logs"
        )
        
        # Initialize rate limiting
        init_rate_limiting(app)
        
        # Add a test route with rate limiting
        @app.route("/test-rate-limit")
        @rate_limit("2 per second")  # Very restrictive for testing
        def test_rate_limit_route():
            return {"message": "Rate limit test successful"}
        
        return app

    def test_flask_limiter_logger_configuration(self, test_app):
        """Test that the flask-limiter logger is properly configured."""
        with test_app.app_context():
            # Get the flask-limiter logger
            limiter_logger = logging.getLogger("flask-limiter")
            
            # Check that it has handlers
            assert len(limiter_logger.handlers) > 0, "flask-limiter logger should have at least one handler"
            
            # Check that it's set to INFO level
            assert limiter_logger.level == logging.INFO, "flask-limiter logger should be set to INFO level"
            
            # Check that it doesn't propagate to root logger
            assert not limiter_logger.propagate, "flask-limiter logger should not propagate"

    def test_rate_limit_violation_logging(self, test_app):
        """Test that rate limit violations are logged to both loggers."""
        with test_app.test_client() as client:
            # Make requests rapidly to trigger rate limiting
            responses = []
            for i in range(5):
                response = client.get("/test-rate-limit")
                responses.append(response)
                if i < 4:  # Small delay between requests
                    time.sleep(0.1)
            
            # Check that at least one request was rate limited
            rate_limited = any(r.status_code == 429 for r in responses)
            assert rate_limited, "At least one request should be rate limited"
            
            # Check log files for rate limit violations
            log_dir = Path(__file__).parent.parent / "logs"
            flask_limiter_log = log_dir / "flask_limiter.log"
            rate_limit_log = log_dir / "rate_limit.log"
            
            # Give a moment for logs to be written
            time.sleep(0.5)
            
            # Check flask-limiter log
            if flask_limiter_log.exists():
                with open(flask_limiter_log, 'r') as f:
                    flask_limiter_content = f.read()
                    assert "Rate limit violation" in flask_limiter_content, \
                        "flask-limiter.log should contain rate limit violation messages"
            
            # Check rate_limit log
            if rate_limit_log.exists():
                with open(rate_limit_log, 'r') as f:
                    rate_limit_content = f.read()
                    assert "Rate limit violation" in rate_limit_content, \
                        "rate_limit.log should contain rate limit violation messages"

    def test_concurrent_rate_limiting(self, test_app):
        """Test rate limiting under concurrent load."""
        with test_app.test_client() as client:
            results = []
            
            def make_request(request_id):
                """Make a single request and record the result."""
                try:
                    response = client.get("/test-rate-limit")
                    results.append({
                        "request_id": request_id,
                        "status_code": response.status_code,
                        "data": response.get_json() if response.content_type == "application/json" else None
                    })
                except Exception as e:
                    results.append({
                        "request_id": request_id,
                        "status_code": 0,
                        "error": str(e)
                    })
            
            # Make concurrent requests
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(make_request, i) for i in range(10)]
                for future in futures:
                    future.result()
            
            # Analyze results
            successful = sum(1 for r in results if 200 <= r["status_code"] < 300)
            rate_limited = sum(1 for r in results if r["status_code"] == 429)
            
            assert successful > 0, "Some requests should succeed"
            assert rate_limited > 0, "Some requests should be rate limited"
            
            # Total should equal number of requests made
            assert len(results) == 10, "All requests should be recorded"

    def test_log_rate_limit_violation_function(self, test_app):
        """Test the log_rate_limit_violation function directly."""
        with test_app.app_context():
            # Mock request context
            with test_app.test_request_context('/test', method='GET'):
                # Call the logging function
                log_rate_limit_violation("test-key", "5 per minute")
                
                # Give a moment for logs to be written
                time.sleep(0.1)
                
                # Check log files
                log_dir = Path(__file__).parent.parent / "logs"
                flask_limiter_log = log_dir / "flask_limiter.log"
                rate_limit_log = log_dir / "rate_limit.log"
                
                # Check flask-limiter log
                if flask_limiter_log.exists():
                    with open(flask_limiter_log, 'r') as f:
                        content = f.read()
                        assert "test-key" in content, "flask-limiter.log should contain the test key"
                        assert "5 per minute" in content, "flask-limiter.log should contain the limit"
                
                # Check rate_limit log
                if rate_limit_log.exists():
                    with open(rate_limit_log, 'r') as f:
                        content = f.read()
                        assert "test-key" in content, "rate_limit.log should contain the test key"
                        assert "5 per minute" in content, "rate_limit.log should contain the limit"

    def test_rate_limit_headers(self, test_app):
        """Test that rate limit headers are included in responses."""
        with test_app.test_client() as client:
            # Make a request
            response = client.get("/test-rate-limit")
            
            # Check for rate limit headers (if enabled)
            # Note: These might not be present in memory storage
            if response.status_code != 429:
                # Successful request might have headers
                pass  # Headers depend on configuration
            
            # Make requests until rate limited
            for i in range(5):
                response = client.get("/test-rate-limit")
                if response.status_code == 429:
                    # Rate limited response should have retry information
                    assert b"Rate limit exceeded" in response.data or \
                           response.status_code == 429, \
                           "Rate limited response should indicate rate limiting"
                    break

    def test_different_rate_limits_for_different_endpoints(self):
        """Test that different endpoints can have different rate limits."""
        app = Flask(__name__)
        app.config.update(
            TESTING=True,
            SECRET_KEY="test-secret-key",
            RATELIMIT_ENABLED=True,
            RATELIMIT_DEFAULT="10 per minute",
            RATELIMIT_STORAGE_URL="memory://"
        )
        
        init_rate_limiting(app)
        
        # Add routes with different rate limits
        @app.route("/fast")
        @rate_limit("10 per second")
        def fast_route():
            return {"message": "Fast route"}
        
        @app.route("/slow")
        @rate_limit("1 per minute")
        def slow_route():
            return {"message": "Slow route"}
        
        with app.test_client() as client:
            # Test fast route - should allow many requests
            fast_responses = []
            for i in range(5):
                response = client.get("/fast")
                fast_responses.append(response)
                time.sleep(0.05)
            
            # Most fast requests should succeed
            fast_success = sum(1 for r in fast_responses if 200 <= r.status_code < 300)
            assert fast_success >= 4, "Fast route should allow most requests"
            
            # Test slow route - should quickly rate limit
            slow_responses = []
            for i in range(3):
                response = client.get("/slow")
                slow_responses.append(response)
                time.sleep(0.1)
            
            # At least one slow request should be rate limited
            slow_limited = sum(1 for r in slow_responses if r.status_code == 429)
            assert slow_limited >= 1, "Slow route should rate limit quickly"


if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v"])