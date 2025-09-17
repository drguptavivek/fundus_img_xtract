#!/usr/bin/env python3
"""
Test script for the stack trace handler.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.stack_trace_handler import log_current_stack, log_stack_trace

def test_function():
    """Test function to generate a stack trace."""
    print("Testing stack trace logging...")
    log_current_stack("Testing current stack trace logging")
    print("Stack trace logged successfully!")

def test_exception_logging():
    """Test logging an exception."""
    try:
        raise ValueError("This is a test exception")
    except Exception as e:
        print("Testing exception logging...")
        log_stack_trace(
            message="Test exception logging",
            exception=e,
            include_locals=True
        )
        print("Exception logged successfully!")

if __name__ == "__main__":
    test_function()
    test_exception_logging()
    print("All tests completed!")