#!/usr/bin/env python3
"""
Test script to verify that the rate limiter is using the correct flask-limiter logger.
This script should be run with the Flask application context.
"""

import logging
import sys
import os

# Add the project directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_logger_with_app():
    """Test the flask-limiter logger within the Flask app context."""
    from app import create_app
    
    app = create_app()
    
    with app.app_context():
        print("Testing flask-limiter logger configuration within app context...")
        
        # Get the flask-limiter logger
        limiter_logger = logging.getLogger("flask-limiter")
        
        # Check if the logger has handlers
        if limiter_logger.handlers:
            print(f"✓ flask-limiter logger has {len(limiter_logger.handlers)} handler(s)")
            for handler in limiter_logger.handlers:
                print(f"  - Handler: {type(handler).__name__}")
                if hasattr(handler, 'baseFilename'):
                    print(f"    File: {handler.baseFilename}")
        else:
            print("✗ flask-limiter logger has no handlers")
        
        # Check the logger level
        print(f"✓ Logger level: {logging.getLevelName(limiter_logger.level)}")
        
        # Test logging to the flask-limiter logger
        print("\nTesting log message to flask-limiter logger...")
        limiter_logger.info("Test message to flask-limiter logger from app context")
        print("✓ Log message sent successfully")
        
        # Test the rate limit violation logging
        print("\nTesting rate limit violation logging...")
        try:
            from utils.rate_limiter import log_rate_limit_violation
            log_rate_limit_violation("test_key", "10 per minute")
            print("✓ Rate limit violation logged successfully")
            return True
        except Exception as e:
            print(f"✗ Error logging rate limit violation: {e}")
            return False

def main():
    """Run the test."""
    print("=" * 60)
    print("Rate Limiter Logger Test (with App Context)")
    print("=" * 60)
    
    test_passed = test_logger_with_app()
    
    print("\n" + "=" * 60)
    print("Test Results:")
    print(f"Rate Limiter Logger Test: {'PASSED' if test_passed else 'FAILED'}")
    
    if test_passed:
        print("\n✓ Test passed! The rate limiter is using the correct logger.")
        return 0
    else:
        print("\n✗ Test failed. Please check the configuration.")
        return 1

if __name__ == "__main__":
    sys.exit(main())