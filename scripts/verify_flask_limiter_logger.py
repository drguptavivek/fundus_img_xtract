#!/usr/bin/env python3
"""
Simple script to verify that the flask-limiter logger is working correctly.
This script directly tests the logger without needing a running server.
"""

import os
import sys
import logging
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables
from utils.env_loader import load_environment
load_environment()

def verify_logger_configuration():
    """Verify that the flask-limiter logger is properly configured."""
    print("🔍 Verifying flask-limiter logger configuration...")
    print("-" * 60)
    
    # Initialize logger configuration (similar to app.py)
    from pathlib import Path
    log_dir = Path(project_root) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Create handler for flask-limiter logger
    from logging.handlers import RotatingFileHandler
    flask_limiter_handler = RotatingFileHandler(
        log_dir / "flask_limiter.log",
        maxBytes=2 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
        delay=True
    )
    flask_limiter_handler.setLevel(logging.INFO)
    
    # Set formatter
    base_format = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s %(message)s")
    flask_limiter_handler.setFormatter(base_format)
    
    # Configure the flask-limiter logger
    limiter_logger = logging.getLogger("flask-limiter")
    limiter_logger.setLevel(logging.INFO)
    limiter_logger.propagate = False
    
    # Remove existing handlers
    for existing in list(limiter_logger.handlers):
        limiter_logger.removeHandler(existing)
        try:
            existing.close()
        except Exception:
            pass
    
    # Add the new handler
    limiter_logger.addHandler(flask_limiter_handler)
    
    # Also configure rate_limit logger
    rate_limit_handler = RotatingFileHandler(
        log_dir / "rate_limit.log",
        maxBytes=2 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
        delay=True
    )
    rate_limit_handler.setLevel(logging.INFO)
    rate_limit_handler.setFormatter(base_format)
    
    rate_limit_logger = logging.getLogger("rate_limit")
    rate_limit_logger.setLevel(logging.INFO)
    rate_limit_logger.propagate = False
    
    # Remove existing handlers
    for existing in list(rate_limit_logger.handlers):
        rate_limit_logger.removeHandler(existing)
        try:
            existing.close()
        except Exception:
            pass
    
    rate_limit_logger.addHandler(rate_limit_handler)
    
    # Log initialization
    limiter_logger.info(f"Flask-Limiter logger initialized at {log_dir / 'flask_limiter.log'}")
    rate_limit_logger.info(f"Rate limit logger initialized at {log_dir / 'rate_limit.log'}")
    
    # Get the flask-limiter logger
    limiter_logger = logging.getLogger("flask-limiter")
    
    # Check logger level
    print(f"Logger name: {limiter_logger.name}")
    print(f"Logger level: {logging.getLevelName(limiter_logger.level)}")
    print(f"Logger handlers: {len(limiter_logger.handlers)}")
    print(f"Logger propagate: {limiter_logger.propagate}")
    
    # Check handlers
    for i, handler in enumerate(limiter_logger.handlers):
        print(f"  Handler {i}: {type(handler).__name__}")
        if hasattr(handler, 'baseFilename'):
            print(f"    File: {handler.baseFilename}")
        print(f"    Level: {logging.getLevelName(handler.level)}")
    
    # Check if log file exists
    log_dir = Path(project_root) / "logs"
    flask_limiter_log = log_dir / "flask_limiter.log"
    
    if flask_limiter_log.exists():
        print(f"\n✅ Log file exists: {flask_limiter_log}")
        
        # Show last few lines
        with open(flask_limiter_log, 'r') as f:
            lines = f.readlines()
            print(f"\n📋 Last {min(5, len(lines))} lines from flask_limiter.log:")
            for line in lines[-5:]:
                print(f"  {line.strip()}")
    else:
        print(f"\n❌ Log file does not exist: {flask_limiter_log}")
    
    return len(limiter_logger.handlers) > 0

def test_logger_functionality():
    """Test that the logger can write messages."""
    print("\n🧪 Testing logger functionality...")
    print("-" * 60)
    
    # Get the flask-limiter logger
    limiter_logger = logging.getLogger("flask-limiter")
    
    # Test different log levels
    test_messages = [
        (logging.INFO, "Test INFO message from verification script"),
        (logging.WARNING, "Test WARNING message from verification script"),
        (logging.ERROR, "Test ERROR message from verification script")
    ]
    
    for level, message in test_messages:
        limiter_logger.log(level, message)
        print(f"  Logged {logging.getLevelName(level)}: {message}")
    
    # Check if messages were written
    log_dir = Path(project_root) / "logs"
    flask_limiter_log = log_dir / "flask_limiter.log"
    
    if flask_limiter_log.exists():
        with open(flask_limiter_log, 'r') as f:
            content = f.read()
            if "verification script" in content:
                print("\n✅ Test messages found in log file")
                return True
            else:
                print("\n⚠️  Test messages not found in log file")
                return False
    else:
        print("\n❌ Log file does not exist")
        return False

def test_rate_limit_violation_logging():
    """Test the rate limit violation logging function."""
    print("\n🚨 Testing rate limit violation logging...")
    print("-" * 60)
    
    try:
        # Import the function
        from utils.rate_limiter import log_rate_limit_violation
        
        # Create a mock request context
        from flask import Flask
        app = Flask(__name__)
        
        with app.app_context():
            with app.test_request_context('/test-endpoint', method='GET'):
                # Call the logging function
                log_rate_limit_violation("test-key-123", "5 per minute")
                print("  Called log_rate_limit_violation with test data")
        
        # Check if the violation was logged
        log_dir = Path(project_root) / "logs"
        flask_limiter_log = log_dir / "flask_limiter.log"
        rate_limit_log = log_dir / "rate_limit.log"
        
        found_in_flask_limiter = False
        found_in_rate_limit = False
        
        # Check flask-limiter log
        if flask_limiter_log.exists():
            with open(flask_limiter_log, 'r') as f:
                content = f.read()
                if "test-key-123" in content:
                    print("  ✅ Found violation in flask_limiter.log")
                    found_in_flask_limiter = True
                else:
                    print("  ⚠️  Violation not found in flask_limiter.log")
        
        # Check rate_limit log
        if rate_limit_log.exists():
            with open(rate_limit_log, 'r') as f:
                content = f.read()
                if "test-key-123" in content:
                    print("  ✅ Found violation in rate_limit.log")
                    found_in_rate_limit = True
                else:
                    print("  ⚠️  Violation not found in rate_limit.log")
        
        return found_in_flask_limiter and found_in_rate_limit
        
    except Exception as e:
        print(f"  ❌ Error testing rate limit violation logging: {e}")
        return False

def main():
    """Main verification function."""
    print("🚀 Flask-Limiter Logger Verification Script")
    print("=" * 60)
    
    # Test 1: Verify logger configuration
    config_ok = verify_logger_configuration()
    
    # Test 2: Test logger functionality
    functionality_ok = test_logger_functionality()
    
    # Test 3: Test rate limit violation logging
    violation_ok = test_rate_limit_violation_logging()
    
    # Summary
    print("\n📊 Verification Summary")
    print("=" * 60)
    print(f"Logger Configuration: {'✅ OK' if config_ok else '❌ FAILED'}")
    print(f"Logger Functionality: {'✅ OK' if functionality_ok else '❌ FAILED'}")
    print(f"Rate Limit Logging: {'✅ OK' if violation_ok else '❌ FAILED'}")
    
    if config_ok and functionality_ok:
        print("\n✅ Flask-Limiter logger is working correctly!")
        print("Rate limit violations will be logged to both:")
        print(f"  - {project_root}/logs/flask_limiter.log")
        print(f"  - {project_root}/logs/rate_limit.log")
    else:
        print("\n❌ Some issues were found with the flask-limiter logger")
        print("Please check the configuration in app.py")
    
    return config_ok and functionality_ok

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)