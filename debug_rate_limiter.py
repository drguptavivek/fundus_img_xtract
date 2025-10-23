#!/usr/bin/env python3
"""
Debug script to check rate limiter initialization and behavior.
"""

import os
import sys
from pathlib import Path

# Add the project root to the path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Set up environment
os.environ.setdefault('FLASK_ENV', 'development')
os.environ.setdefault('RATELIMIT_ENABLED', 'true')
os.environ.setdefault('RATELIMIT_STORAGE_URI', 'memory://')
os.environ.setdefault('RATELIMIT_DEFAULT', '500 per hour, 50 per minute')

from flask import Flask, jsonify
from utils.rate_limiter import init_rate_limiting, rate_limit

def create_test_app():
    """Create a test Flask app with rate limiting."""
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret-key",
        WTF_CSRF_ENABLED=False,
        RATELIMIT_ENABLED=True,
        RATELIMIT_STORAGE_URI='memory://',
        RATELIMIT_DEFAULT='500 per hour, 50 per minute',
        RATELIMIT_HEADERS_ENABLED=True,
        RATELIMIT_SWALLOW_ERRORS=False
    )
    
    # Initialize rate limiting
    init_rate_limiting(app)
    
    # Add a test route
    @app.route('/test')
    @rate_limit("10 per minute")
    def test_route():
        return jsonify({"message": "success"})
    
    return app

def main():
    """Main function to debug rate limiter."""
    print("Creating test app...")
    app = create_test_app()
    
    # Import limiter after app creation to get the updated global
    from utils.rate_limiter import limiter
    print(f"Limiter initialized: {limiter is not None}")
    if limiter:
        print(f"Limiter storage type: {type(limiter._storage).__name__}")
        print(f"Limiter storage URI: {limiter._storage_uri}")
    
    print(f"App extensions: {app.extensions}")
    if 'limiter' in app.extensions:
        limiter_set = app.extensions['limiter']
        print(f"Limiter in extensions: {limiter_set}")
        if isinstance(limiter_set, set) and limiter_set:
            current_limiter = next(iter(limiter_set))
            print(f"Current limiter: {current_limiter}")
            print(f"Current limiter storage type: {type(current_limiter._storage).__name__}")
    
    with app.test_client() as client:
        print("\nMaking requests...")
        for i in range(5):
            response = client.get('/test')
            print(f"Request {i+1}: Status {response.status_code}")
            if response.status_code == 429:
                print(f"Response data: {response.get_json()}")
                break
            elif response.status_code == 200:
                print(f"Response data: {response.get_json()}")

if __name__ == '__main__':
    main()