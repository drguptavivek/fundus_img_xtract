#!/usr/bin/env python3
"""
Test runner for Flask-Limiter 4.0 tests.
Provides options to run unit tests, integration tests, and end-to-end tests.
"""

import os
import sys
import argparse
import subprocess
from pathlib import Path

# Add the project root to the path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def run_unit_tests():
    """Run unit tests for rate limiter."""
    print("=" * 60)
    print("RUNNING UNIT TESTS")
    print("=" * 60)
    
    cmd = [sys.executable, "-m", "pytest", "tests/test_rate_limiter_unit.py", "-v"]
    
    try:
        result = subprocess.run(cmd, cwd=project_root, capture_output=False)
        return result.returncode == 0
    except Exception as e:
        print(f"Error running unit tests: {e}")
        return False


def run_integration_tests():
    """Run integration tests for rate limiter."""
    print("=" * 60)
    print("RUNNING INTEGRATION TESTS")
    print("=" * 60)
    
    cmd = [sys.executable, "-m", "pytest", "tests/test_rate_limiter_integration.py", "-v"]
    
    try:
        result = subprocess.run(cmd, cwd=project_root, capture_output=False)
        return result.returncode == 0
    except Exception as e:
        print(f"Error running integration tests: {e}")
        return False


def run_e2e_tests():
    """Run end-to-end tests for rate limiter."""
    print("=" * 60)
    print("RUNNING END-TO-END TESTS")
    print("=" * 60)
    print("Note: Make sure the application is running before executing E2E tests.")
    print(f"Expected URL: {os.getenv('BASE_URL', 'http://127.0.0.1')}:{os.getenv('FLASK_PORT', '5001')}")
    print("-" * 60)
    
    cmd = [sys.executable, "tests/test_rate_limiter_e2e.py"]
    
    try:
        result = subprocess.run(cmd, cwd=project_root, capture_output=False)
        return result.returncode == 0
    except Exception as e:
        print(f"Error running E2E tests: {e}")
        return False


def run_all_tests():
    """Run all rate limiter tests."""
    print("=" * 60)
    print("RUNNING ALL RATE LIMITER TESTS")
    print("=" * 60)
    
    results = {
        "unit": run_unit_tests(),
        "integration": run_integration_tests(),
        "e2e": run_e2e_tests()
    }
    
    print("\n" + "=" * 60)
    print("TEST RESULTS SUMMARY")
    print("=" * 60)
    
    for test_type, passed in results.items():
        status = "PASSED" if passed else "FAILED"
        print(f"{test_type.upper()} Tests: {status}")
    
    all_passed = all(results.values())
    print("\n" + ("✅ ALL TESTS PASSED" if all_passed else "❌ SOME TESTS FAILED"))
    
    return all_passed


def check_app_running():
    """Check if the Flask application is running."""
    import requests
    from dotenv import load_dotenv
    
    # Environment is already loaded by utils.env_loader
    
    base_url = os.getenv("BASE_URL", "http://127.0.0.1")
    flask_port = os.getenv("FLASK_PORT", "5001")
    health_url = f"{base_url}:{flask_port}/healthz"
    
    try:
        response = requests.get(health_url, timeout=5)
        return response.status_code == 200
    except:
        return False


def main():
    """Main function to run tests based on command line arguments."""
    parser = argparse.ArgumentParser(
        description="Flask-Limiter 4.0 Test Runner",
        epilog="""
Rate limit management commands:
  uv run scripts/manage_rate_limits.py list
  uv run scripts/manage_rate_limits.py status [--key <key>]
  uv run scripts/manage_rate_limits.py clear --key <key> [--limit <limit>]
  uv run scripts/manage_rate_limits.py clear-all
  uv run scripts/manage_rate_limits.py my-key
        """
    )
    parser.add_argument(
        "test_type",
        choices=["unit", "integration", "e2e", "all"],
        help="Type of tests to run"
    )
    parser.add_argument(
        "--check-app",
        action="store_true",
        help="Check if the app is running before running E2E tests"
    )
    
    args = parser.parse_args()
    
    if args.test_type == "unit":
        success = run_unit_tests()
    elif args.test_type == "integration":
        success = run_integration_tests()
    elif args.test_type == "e2e":
        if args.check_app:
            print("Checking if Flask application is running...")
            if check_app_running():
                print("✅ Flask application is running")
            else:
                print("❌ Flask application is not running!")
                print("Please start the application with: uv run app.py")
                return False
        success = run_e2e_tests()
    elif args.test_type == "all":
        success = run_all_tests()
    else:
        print(f"Unknown test type: {args.test_type}")
        return False
    
    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)