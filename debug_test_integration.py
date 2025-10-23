#!/usr/bin/env python3
"""
Debug script to test rate limiting decorators exactly like the integration tests.
"""

import sys
import os
from pathlib import Path

# Add the project root directory to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Mock the environment to match test configuration
os.environ['RATELIMIT_ENABLED'] = 'true'
os.environ['RATELIMIT_STORAGE_URI'] = 'memory://'
os.environ['REDIS_URL'] = 'memory://'
os.environ['RATELIMIT_DEFAULT'] = '500 per hour, 50 per minute'
os.environ['RATELIMIT_APPLICATION'] = '1000 per hour, 100 per minute'
os.environ['RATELIMIT_SWALLOW_ERRORS'] = 'false'

from app import create_app
from flask import jsonify
from utils.rate_limiter import (
    auth_rate_limit,
    upload_rate_limit,
    api_rate_limit,
    admin_rate_limit,
    clear_rate_limit,
    limiter
)

def test_auth_rate_limit_decorator():
    """Test auth rate limit decorator exactly like the integration test."""
    # Create a test app
    app = create_app()
    app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret-key",
        WTF_CSRF_ENABLED=False,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        LOGIN_DISABLED=True,  # Disable login for testing
        # Enable rate limiting for testing
        RATELIMIT_ENABLED='true',
        RATELIMIT_STORAGE_URI='memory://',
        REDIS_URL='memory://',  # Override Redis URL to use memory
        RATELIMIT_DEFAULT='500 per hour, 50 per minute',
        RATELIMIT_APPLICATION='1000 per hour, 100 per minute',
        RATELIMIT_SWALLOW_ERRORS='false'  # Don't swallow errors so we can see what's happening
    )
    
    print(f"Limiter initialized: {limiter is not None}")
    if limiter:
        print(f"Limiter storage type: {type(limiter._storage).__name__ if limiter._storage else 'None'}")
        print(f"Limiter storage URI: {getattr(limiter, '_storage_uri', 'Unknown')}")
    
    # Register the route before creating the test client
    @app.route('/test-auth-rate-limit', methods=['POST'])
    @auth_rate_limit("3 per minute")
    def test_auth_route():
        return jsonify({"message": "auth success"})
    
    # Clear any existing rate limits
    with app.app_context():
        print("\nClearing rate limits...")
        result = clear_rate_limit()
        print(f"Clear rate limit result: {result}")
    
    with app.test_client() as client:
        # Make multiple POST requests
        responses = []
        for i in range(5):
            response = client.post('/test-auth-rate-limit')
            responses.append(response)
            print(f"Request {i+1}: Status {response.status_code}")
            if response.status_code == 429:
                break
        
        # Check results
        success_count = sum(1 for r in responses if r.status_code == 200)
        redirect_count = sum(1 for r in responses if r.status_code == 302)
        rate_limited_count = sum(1 for r in responses if r.status_code == 429)
        
        print(f"\nResults: {success_count} successful, {redirect_count} redirects, {rate_limited_count} rate limited")
        
        # Should get at least some successful responses or redirects (auth might be required)
        if success_count > 0 or redirect_count > 0:
            print("✓ Test passed: Got successful responses or redirects")
        else:
            print("✗ Test failed: No successful responses or redirects")
        
        # Should eventually get rate limited
        if rate_limited_count > 0:
            print("✓ Test passed: Got rate limited")
        else:
            print("✗ Test failed: No rate limiting")

def test_api_rate_limit_decorator():
    """Test API rate limit decorator exactly like the integration test."""
    # Create a test app
    app = create_app()
    app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret-key",
        WTF_CSRF_ENABLED=False,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        LOGIN_DISABLED=True,  # Disable login for testing
        # Enable rate limiting for testing
        RATELIMIT_ENABLED='true',
        RATELIMIT_STORAGE_URI='memory://',
        REDIS_URL='memory://',  # Override Redis URL to use memory
        RATELIMIT_DEFAULT='500 per hour, 50 per minute',
        RATELIMIT_APPLICATION='1000 per hour, 100 per minute',
        RATELIMIT_SWALLOW_ERRORS='false'  # Don't swallow errors so we can see what's happening
    )
    
    # Register the route before creating the test client
    @app.route('/api/test-api-rate-limit')
    @api_rate_limit("8 per minute")
    def test_api_route():
        return jsonify({"message": "api success"})
    
    # Clear any existing rate limits
    with app.app_context():
        print("\nClearing rate limits...")
        result = clear_rate_limit()
        print(f"Clear rate limit result: {result}")
    
    with app.test_client() as client:
        # Make multiple requests
        responses = []
        for i in range(10):
            response = client.get('/api/test-api-rate-limit')
            responses.append(response)
            print(f"Request {i+1}: Status {response.status_code}")
            if response.status_code == 429:
                break
        
        # Check results
        success_count = sum(1 for r in responses if r.status_code == 200)
        redirect_count = sum(1 for r in responses if r.status_code == 302)
        rate_limited_count = sum(1 for r in responses if r.status_code == 429)
        
        print(f"\nResults: {success_count} successful, {redirect_count} redirects, {rate_limited_count} rate limited")
        
        # Should get at least some successful responses or redirects (auth might be required)
        if success_count > 0 or redirect_count > 0:
            print("✓ Test passed: Got successful responses or redirects")
        else:
            print("✗ Test failed: No successful responses or redirects")
        
        # Should eventually get rate limited
        if rate_limited_count > 0:
            print("✓ Test passed: Got rate limited")
        else:
            print("✗ Test failed: No rate limiting")

if __name__ == "__main__":
    print("Testing auth_rate_limit decorator...")
    test_auth_rate_limit_decorator()
    
    print("\n" + "="*50 + "\n")
    
    print("Testing api_rate_limit decorator...")
    test_api_rate_limit_decorator()