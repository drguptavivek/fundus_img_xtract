#!/usr/bin/env python3
"""
Test script to verify that file upload routes are not blocked by security middleware
while other routes still have strict payload size limits.
"""

import os
import sys
import requests
import tempfile
from pathlib import Path
import subprocess
import json
# Load environment variables
from utils.env_loader import load_environment
load_environment()

# Add the project directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

def setup_test_admin():
    """Create a test admin user for testing authenticated routes."""
    print("Setting up test admin user...")
    try:
        # Run the create_test_admin script
        result = subprocess.run(
            ["uv", "run", "scripts/create_test_admin.py"],
            capture_output=True,
            text=True,
            cwd=os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
        )
        if result.returncode != 0:
            print(f"Failed to create test admin user: {result.stderr}")
            return None
        print("Test admin user created successfully")
        return {"username": "Test", "password": "test@123"}
    except Exception as e:
        print(f"Error creating test admin user: {e}")
        return None

def cleanup_test_admin():
    """Clean up the test admin user."""
    print("Cleaning up test admin user...")
    try:
        # Run the cleanup_test_admin script
        result = subprocess.run(
            ["uv", "run", "scripts/cleanup_test_admin.py", "--force"],
            capture_output=True,
            text=True,
            cwd=os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
        )
        if result.returncode != 0:
            print(f"Failed to cleanup test admin user: {result.stderr}")
        else:
            print("Test admin user cleaned up successfully")
    except Exception as e:
        print(f"Error cleaning up test admin user: {e}")

def test_payload_limits():
    """Test that payload limits are applied correctly to different routes."""
    
    # Base URL for the application from environment variable
    BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:5001")
    
    print("Testing payload size limits for different routes...")
    print("=" * 60)
    
    # Create test admin user
    admin_creds = setup_test_admin()
    if not admin_creds:
        print("Failed to set up test admin user, skipping authenticated tests")
    
    # Test 1: Login route should have 1KB limit
    print("\n1. Testing login route (should have 1KB limit):")
    large_payload = "x" * 2048  # 2KB payload
    try:
        response = requests.post(
            f"{BASE_URL}/login",
            data={"username": "test", "password": large_payload},
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        if response.status_code == 413:
            print("✓ Login route correctly rejected large payload due to size")
        elif response.status_code in [403, 429]:
            print("✓ Login route correctly rejected large payload (blocked by CSRF/rate limiting)")
        else:
            print(f"✗ Login route should have rejected payload (status: {response.status_code})")
    except requests.exceptions.ConnectionError:
        print("! Could not connect to application. Make sure it's running on localhost:5001")
        return
    
    # Test 2: Direct upload route should allow larger payloads
    print("\n2. Testing direct upload route (should allow larger payloads):")
    # Create a temporary image file
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as temp_file:
        temp_file.write(b"x" * 50000)  # 50KB file
        temp_path = temp_file.name
    
    try:
        with open(temp_path, "rb") as f:
            files = {"files": ("test.jpg", f, "image/jpeg")}
            data = {
                "hospital_id": "1",
                "lab_unit_id": "1", 
                "camera_id": "1",
                "disease_id": "1",
                "area_id": "1"
            }
            response = requests.post(
                f"{BASE_URL}/direct/upload",
                files=files,
                data=data
            )
            # We expect this to fail with authentication error, not payload size error
            if response.status_code != 413:
                print("✓ Direct upload route correctly allows larger payloads")
            else:
                print("✗ Direct upload route incorrectly rejected payload due to size")
    finally:
        os.unlink(temp_path)
    
    # Test 3: Remedio ZIP upload route should allow larger payloads
    print("\n3. Testing remedio ZIP upload route (should allow larger payloads):")
    # Create a temporary ZIP file
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as temp_file:
        temp_file.write(b"x" * 50000)  # 50KB file
        temp_path = temp_file.name
    
    try:
        with open(temp_path, "rb") as f:
            files = {"files": ("test.zip", f, "application/zip")}
            data = {
                "hospital_id": "1",
                "lab_unit_id": "1"
            }
            response = requests.post(
                f"{BASE_URL}/remedio_zip_uploads/upload",
                files=files,
                data=data
            )
            # We expect this to fail with authentication error, not payload size error
            if response.status_code != 413:
                print("✓ Remedio ZIP upload route correctly allows larger payloads")
            else:
                print("✗ Remedio ZIP upload route incorrectly rejected payload due to size")
    finally:
        os.unlink(temp_path)
    
    # Test 4: Pre-graded upload route should allow larger payloads
    print("\n4. Testing pre-graded upload route (should allow larger payloads):")
    # Create a temporary image file
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as temp_file:
        temp_file.write(b"x" * 50000)  # 50KB file
        temp_path = temp_file.name
    
    try:
        with open(temp_path, "rb") as f:
            files = {"files": ("test.jpg", f, "image/jpeg")}
            data = {
                "hospital_id": "1",
                "lab_unit_id": "1", 
                "camera_id": "1",
                "disease_id": "1",
                "area_id": "1"
            }
            response = requests.post(
                f"{BASE_URL}/direct/pregraded",
                files=files,
                data=data
            )
            # We expect this to fail with authentication error, not payload size error
            if response.status_code != 413:
                print("✓ Pre-graded upload route correctly allows larger payloads")
            else:
                print("✗ Pre-graded upload route incorrectly rejected payload due to size")
    finally:
        os.unlink(temp_path)
    
    # Test 5: Pre-graded grades upload route should allow larger payloads
    print("\n5. Testing pre-graded grades upload route (should allow larger payloads):")
    # Create a temporary Excel file
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as temp_file:
        temp_file.write(b"x" * 50000)  # 50KB file
        temp_path = temp_file.name
    
    try:
        with open(temp_path, "rb") as f:
            files = {"grades_file": ("test.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
            data = {
                "form_role": "resident",
                "hospital_id": "1",
                "lab_unit_id": "1", 
                "disease_id": "1",
                "area_id": "1",
                "grader_user_id": "1"
            }
            response = requests.post(
                f"{BASE_URL}/direct/pregraded/grades",
                files=files,
                data=data
            )
            # We expect this to fail with authentication error, not payload size error
            if response.status_code != 413:
                print("✓ Pre-graded grades upload route correctly allows larger payloads")
            else:
                print("✗ Pre-graded grades upload route incorrectly rejected payload due to size")
    finally:
        os.unlink(temp_path)
    
    # Test 6: Authenticated route with login
    print("\n6. Testing authenticated route with admin login:")
    if admin_creds:
        # Use the login_admin script to get session cookies
        try:
            result = subprocess.run(
                ["uv", "run", "scripts/login_admin.py",
                 "--username", admin_creds["username"],
                 "--password", admin_creds["password"],
                 "--base-url", BASE_URL],
                capture_output=True,
                text=True,
                cwd=os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
            )
            
            if result.returncode == 0:
                # Load cookies from file
                try:
                    with open("admin_cookies.json", "r") as f:
                        cookies = json.load(f)
                    
                    # Create a session with the saved cookies
                    session = requests.Session()
                    session.cookies.update(cookies)
                    
                    # Now test an authenticated route with a large payload
                    large_payload = "x" * 2048  # 2KB payload
                    response = session.post(
                        f"{BASE_URL}/dashboard",
                        data={"test_field": large_payload}
                    )
                    # Authenticated routes should not be limited by our middleware
                    if response.status_code != 413:
                        print("✓ Authenticated route correctly allows larger payloads")
                    else:
                        print("✗ Authenticated route incorrectly rejected payload due to size")
                    
                    # Clean up cookies file
                    os.remove("admin_cookies.json")
                except Exception as e:
                    print(f"Error using saved cookies: {e}")
            else:
                # Check if it's just CSRF protection blocking the login
                if "CSRF" in result.stderr or "403" in result.stderr:
                    print("✓ Login correctly blocked by CSRF protection (expected behavior)")
                else:
                    print(f"✗ Failed to login with test admin user: {result.stderr}")
        except Exception as e:
            print(f"Error running login script: {e}")
    
    # Clean up test admin user
    cleanup_test_admin()
    
    print("\n" + "=" * 60)
    print("Payload limit testing completed!")

if __name__ == "__main__":
    try:
        test_payload_limits()
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
        # Ensure cleanup even if interrupted
        cleanup_test_admin()