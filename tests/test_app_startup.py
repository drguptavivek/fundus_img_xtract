"""Test app startup."""

import pytest
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app


def test_app_startup():
    """Test that the app starts without errors."""
    try:
        app = create_app()
        assert app is not None
        assert app.name == 'app'
        # Test that blueprints are registered
        assert 'auth' in app.blueprints
        assert 'uploads' in app.blueprints
        # Add more blueprint assertions as needed
        return True
    except Exception as e:
        pytest.fail(f"App failed to start: {e}")


if __name__ == "__main__":
    test_app_startup()