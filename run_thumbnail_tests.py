#!/usr/bin/env python3
"""
Thumbnail System Test Runner

Comprehensive test runner for the thumbnail system with different test suites:
- Unit tests
- Integration tests
- Performance tests
- Security tests
- Cleanup tests
- Load tests

Usage:
    python run_thumbnail_tests.py [test_type]

    test_type options:
        unit        - Run unit tests only
        integration - Run integration tests only
        performance - Run performance tests only
        security    - Run security tests only
        cleanup     - Run cleanup tests only
        load        - Run load tests only
        all         - Run all tests (default)
"""

import sys
import os
import subprocess
import time
from pathlib import Path

def run_command(cmd, description):
    """Run a command and capture output."""
    print(f"\n{'='*60}")
    print(f"Running: {description}")
    print(f"Command: {' '.join(cmd)}")
    print(f"{'='*60}")

    start_time = time.time()

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent
        )

        end_time = time.time()
        duration = end_time - start_time

        print(f"Duration: {duration:.2f} seconds")
        print(f"Exit code: {result.returncode}")

        if result.stdout:
            print("\nSTDOUT:")
            print(result.stdout)

        if result.stderr:
            print("\nSTDERR:")
            print(result.stderr)

        return result.returncode == 0, duration

    except Exception as e:
        print(f"Error running command: {e}")
        return False, 0

def run_test_suite(test_type, tests_dir):
    """Run a specific test suite."""
    test_files = {
        'unit': [
            'test_thumbnail_image_processing.py',
            'test_thumbnail_file_management.py',
        ],
        'integration': [
            'test_thumbnail_integration.py',
        ],
        'performance': [
            'test_thumbnail_performance.py',
        ],
        'security': [
            'test_thumbnail_security.py',
        ],
        'cleanup': [
            'test_thumbnail_cleanup.py',
        ],
        'load': [
            'test_thumbnail_load.py',
        ],
        'all': [
            'test_thumbnail_*.py',
        ]
    }

    if test_type not in test_files:
        print(f"Unknown test type: {test_type}")
        print(f"Available types: {', '.join(test_files.keys())}")
        return False, 0

    files_to_test = test_files[test_type]
    total_duration = 0
    all_passed = True

    for test_file in files_to_test:
        test_path = os.path.join(tests_dir, test_file)

        if not os.path.exists(test_path):
            print(f"Test file not found: {test_path}")
            continue

        cmd = [
            sys.executable, '-m', 'pytest',
            test_path,
            '-v',
            '--tb=short',
            '--color=yes'
        ]

        passed, duration = run_command(cmd, f"Running {test_file}")
        total_duration += duration

        if not passed:
            all_passed = False

    return all_passed, total_duration

def main():
    """Main test runner."""
    # Get test type from command line or default to 'all'
    test_type = sys.argv[1] if len(sys.argv) > 1 else 'all'

    print("🧪 Thumbnail System Test Runner")
    print("=" * 60)
    print(f"Test Type: {test_type.upper()}")
    print(f"Python Version: {sys.version}")
    print(f"Working Directory: {os.getcwd()}")
    print("=" * 60)

    # Check if tests directory exists
    tests_dir = os.path.join(os.path.dirname(__file__), 'tests')
    if not os.path.exists(tests_dir):
        print(f"❌ Tests directory not found: {tests_dir}")
        return 1

    # Check if pytest is available
    try:
        import pytest
        print(f"✅ Pytest version: {pytest.__version__}")
    except ImportError:
        print("❌ Pytest not found. Install with: pip install pytest")
        return 1

    # Check required test dependencies
    required_modules = [
        'PIL', 'psutil', 'pytest', 'requests'
    ]

    missing_modules = []
    for module in required_modules:
        try:
            __import__(module)
            print(f"✅ {module}")
        except ImportError:
            print(f"❌ {module} (missing)")
            missing_modules.append(module)

    if missing_modules:
        print(f"\n❌ Missing required modules: {', '.join(missing_modules)}")
        print(f"Install with: pip install {' '.join(missing_modules)}")
        return 1

    print("\n" + "=" * 60)

    # Run the test suite
    start_time = time.time()
    all_passed, total_duration = run_test_suite(test_type, tests_dir)
    end_time = time.time()

    # Print summary
    print(f"\n{'='*60}")
    print("📊 TEST SUMMARY")
    print(f"{'='*60}")
    print(f"Test Suite: {test_type.upper()}")
    print(f"Total Duration: {total_duration:.2f} seconds")
    print(f"Clock Time: {end_time - start_time:.2f} seconds")

    if all_passed:
        print("✅ ALL TESTS PASSED")
        print("\n🎉 Thumbnail system is working correctly!")
        return_code = 0
    else:
        print("❌ SOME TESTS FAILED")
        print("\n⚠️  Please review the test output above for details.")
        return_code = 1

    # Additional recommendations based on test type
    if test_type == 'all' and all_passed:
        print(f"\n💡 RECOMMENDATIONS:")
        print(f"   • All test suites passed successfully")
        print(f"   • The thumbnail system is ready for production")
        print(f"   • Consider running individual suites for detailed analysis")
        print(f"   • Monitor performance in production environment")

    return return_code

if __name__ == '__main__':
    sys.exit(main())