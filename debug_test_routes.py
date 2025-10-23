#!/usr/bin/env python3
"""
Debug script to test rate limiting with routes in the test environment.
"""

import sys
import os
from pathlib import Path

# Add the project root directory to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from flask import Flask, jsonify
from utils.rate_limiter import (
    init_rate_limiting,
    rate_limit,
    auth_rate_limit,
    upload_rate_limit,
    api_rate_limit,
    admin_rate_limit,
    limiter
)

def create_test_app():
    """Create a test app with rate limiting enabled."""
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret-key",
        WTF_CSRF_ENABLED=False,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        LOGIN_DISABLED=False,
        # Enable rate limiting for testing
        RATELIMIT_ENABLED='true',
        RATELIMIT_STORAGE_URI='memory://',
        RATELIMIT_DEFAULT='500 per hour, 50 per minute',
        RATELIMIT_APPLICATION='1000 per hour, 100 per minute',
        RATELIMIT_SWALLOW_ERRORS='false'  # Don't swallow errors so we can see what's happening
    )
    
    # Initialize rate limiting
    init_rate_limiting(app)
    
    # Register test routes
    @app.route('/test-rate-limit')
    @rate_limit("10 per minute")
    def test_rate_limit():
        return jsonify({"message": "rate limit success"})
    
    @app.route('/test-auth-rate-limit', methods=['POST'])
    @auth_rate_limit("3 per minute")
    def test_auth_rate_limit():
        return jsonify({"message": "auth rate limit success"})
    
    @app.route('/test-upload-rate-limit', methods=['POST'])
    @upload_rate_limit("5 per minute")
    def test_upload_rate_limit():
        return jsonify({"message": "upload rate limit success"})
    
    @app.route('/api/test-api-rate-limit')
    @api_rate_limit("8 per minute")
    def test_api_rate_limit():
        return jsonify({"message": "api rate limit success"})
    
    @app.route('/test-admin-rate-limit')
    @admin_rate_limit("6 per minute")
    def test_admin_rate_limit():
        return jsonify({"message": "admin rate limit success"})
    
    return app

def test_decorators():
    """Test the rate limit decorators."""
    app = create_test_app()
    
    print(f"Limiter initialized: {limiter is not None}")
    if limiter:
        print(f"Limiter storage type: {type(limiter._storage).__name__ if limiter._storage else 'None'}")
    
    with app.test_client() as client:
        # Test basic rate limit decorator
        print("\nTesting basic rate_limit decorator...")
        for i in range(15):
            response = client.get('/test-rate-limit')
            print(f"Request {i+1}: Status {response.status_code}")
            if response.status_code == 429:
                break
        
        # Test auth rate limit decorator
        print("\nTesting auth_rate_limit decorator...")
        for i in range(5):
            response = client.post('/test-auth-rate-limit')
            print(f"Request {i+1}: Status {response.status_code}")
            if response.status_code == 429:
                break
        
        # Test upload rate limit decorator
        print("\nTesting upload_rate_limit decorator...")
        for i in range(7):
            response = client.post('/test-upload-rate-limit')
            print(f"Request {i+1}: Status {response.status_code}")
            if response.status_code == 429:
                break
        
        # Test API rate limit decorator
        print("\nTesting api_rate_limit decorator...")
        for i in range(10):
            response = client.get('/api/test-api-rate-limit')
            print(f"Request {i+1}: Status {response.status_code}")
            if response.status_code == 429:
                break
        
        # Test admin rate limit decorator
        print("\nTesting admin_rate_limit decorator...")
        for i in range(8):
            response = client.get('/test-admin-rate-limit')
            print(f"Request {i+1}: Status {response.status_code}")
            if response.status_code == 429:
                break

if __name__ == "__main__":
    test_decorators()