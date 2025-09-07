#!/usr/bin/env python3
"""
Test script to check for application startup errors.
"""

import sys
import os
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

def test_app_startup():
    """Test if the application can start without errors."""
    try:
        # Try to import the app
        import app
        print("✅ App module imported successfully")
        
        # Try to create the app
        flask_app = app.create_app()
        print("✅ Flask app created successfully")
        
        # Try to access some basic attributes
        print(f"✅ App name: {flask_app.name}")
        print(f"✅ App blueprints: {list(flask_app.blueprints.keys())}")
        
        # Check if dual_grading blueprint is registered
        if 'dual_grading' in flask_app.blueprints:
            print("✅ Dual grading blueprint registered successfully")
        else:
            print("❌ Dual grading blueprint not found")
            
        # Check if grading blueprint is registered
        if 'grading' in flask_app.blueprints:
            print("✅ Grading blueprint registered successfully")
        else:
            print("❌ Grading blueprint not found")
            
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"❌ Startup error: {e}")
        return False

if __name__ == "__main__":
    print("Testing application startup...")
    success = test_app_startup()
    if success:
        print("\n🎉 All tests passed! Application should start successfully.")
        sys.exit(0)
    else:
        print("\n💥 Application startup test failed!")
        sys.exit(1)