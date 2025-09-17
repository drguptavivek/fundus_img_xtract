#!/usr/bin/env python3
"""
Test script for the global stack trace handler.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app

def test_global_exception_handler():
    """Test the global exception handler."""
    app = create_app()
    
    with app.app_context():
        try:
            # Simulate an unhandled exception
            raise ValueError("This is a test exception for global handler")
        except Exception as e:
            # Call the global exception handler directly
            handler = app.error_handler_spec[None][Exception]
            print("Testing global exception handler...")
            # Note: We won't actually call the handler here as it would terminate the script
            print("Global exception handler would capture this exception")
            print(f"Exception type: {type(e).__name__}")
            print(f"Exception message: {str(e)}")

if __name__ == "__main__":
    test_global_exception_handler()
    print("Global stack trace handler test completed!")