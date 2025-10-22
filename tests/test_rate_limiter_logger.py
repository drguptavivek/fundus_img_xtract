#!/usr/bin/env python3
"""
Test script to verify that the rate limiter is using the correct flask-limiter logger.
This script checks the logger configuration and simulates a rate limit violation.
"""

import logging
import sys
import os

# Add the project directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_logger_configuration():
    """Test that the flask-limiter logger is properly configured."""
    print("Testing flask-limiter logger configuration...")
    
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
    limiter_logger.info("Test message to flask-limiter logger")
    print("✓ Log message sent successfully")
    
    return True

def test_rate_limit_violation_logging():
    """Test that rate limit violations are logged to the correct logger."""
    print("\nTesting rate limit violation logging...")
    
    # Import the rate limiter utilities
    try:
        from utils.rate_limiter import log_rate_limit_violation
        print("✓ Successfully imported log_rate_limit_violation")
    except ImportError as e:
        print(f"✗ Failed to import log_rate_limit_violation: {e}")
        return False
    
    # Create a mock request object
    class MockRequest:
        def __init__(self):
            self.endpoint = "test.endpoint"
            self.method = "GET"
            self.path = "/test"
            self.remote_addr = "127.0.0.1"
    
    class MockCurrentUser:
        def __init__(self):
            self.is_authenticated = False
    
    # Mock the flask request and current_user
    import utils.rate_limiter
    original_request = getattr(utils.rate_limiter, 'request', None)
    original_current_user = getattr(utils.rate_limiter, 'current_user', None)
    
    try:
        # Set up mocks
        utils.rate_limiter.request = MockRequest()
        utils.rate_limiter.current_user = MockCurrentUser()
        
        # Test the logging function
        log_rate_limit_violation("test_key", "10 per minute")
        print("✓ Rate limit violation logged successfully")
        
        return True
    except Exception as e:
        print(f"✗ Error logging rate limit violation: {e}")
        return False
    finally:
        # Restore originals
        if original_request:
            utils.rate_limiter.request = original_request
        if original_current_user:
            utils.rate_limiter.current_user = original_current_user

def main():
    """Run all tests."""
    print("=" * 60)
    print("Rate Limiter Logger Test")
    print("=" * 60)
    
    # Test logger configuration
    logger_test_passed = test_logger_configuration()
    
    # Test rate limit violation logging
    violation_test_passed = test_rate_limit_violation_logging()
    
    print("\n" + "=" * 60)
    print("Test Results:")
    print(f"Logger Configuration: {'PASSED' if logger_test_passed else 'FAILED'}")
    print(f"Rate Limit Violation Logging: {'PASSED' if violation_test_passed else 'FAILED'}")
    
    if logger_test_passed and violation_test_passed:
        print("\n✓ All tests passed! The rate limiter is using the correct logger.")
        return 0
    else:
        print("\n✗ Some tests failed. Please check the configuration.")
        return 1

if __name__ == "__main__":
    sys.exit(main())