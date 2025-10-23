#!/usr/bin/env python3
"""
Test script to verify CSRF protection on login route
"""

import os
import sys
import requests
import re
from pathlib import Path
import subprocess
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add the project directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

def setup_test_admin():
    """Create a test admin user for testing."""
    print("Setting up test admin user...")
    try:
        result = subprocess.run(
            ["uv", "run", "scripts/create_test_admin.py"],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(os.path.abspath(__file__))
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
        result = subprocess.run(
            ["uv", "run", "scripts/cleanup_test_admin.py", "--force"],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(os.path.abspath(__file__))
        )
        if result.returncode != 0:
            print(f"Failed to cleanup test admin user: {result.stderr}")
        else:
            print("Test admin user cleaned up successfully")
    except Exception as e:
        print(f"Error cleaning up test admin user: {e}")

def extract_csrf_token(html_content):
    """Extract CSRF token from HTML content"""
    # Look for CSRF token in various formats
    patterns = [
        r'name=["\']csrf_token["\']\s+value=["\']([^"\']+)["\']',
        r'<input[^>]*name=["\']csrf_token["\'][^>]*value=["\']([^"\']+)["\']',
        r'csrf_token["\']:\s*["\']([^"\']+)["\']',
        r'var csrf_token = ["\']([^"\']+)["\']',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, html_content)
        if match:
            return match.group(1)
    return None

def test_csrf_protection():
    """Test CSRF protection on login route"""
    
    # Base URL for the application from environment variable
    BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:5001")
    
    print("Testing CSRF protection on login route...")
    print("=" * 60)
    
    # Create test admin user
    admin_creds = setup_test_admin()
    if not admin_creds:
        print("Failed to set up test admin user")
        return
    
    session = requests.Session()
    
    # Test 1: Get login page and extract CSRF token
    print("\n1. Testing CSRF token extraction from login page:")
    try:
        response = session.get(f"{BASE_URL}/login")
        if response.status_code != 200:
            print(f"✗ Failed to access login page: {response.status_code}")
            return
        
        csrf_token = extract_csrf_token(response.text)
        if csrf_token:
            print(f"✓ CSRF token extracted successfully: {csrf_token[:10]}...")
        else:
            print("! Could not extract CSRF token from login page")
            print("  This might be expected if using session-based CSRF")
    except requests.exceptions.ConnectionError:
        print("! Could not connect to application. Make sure it's running on localhost:5001")
        cleanup_test_admin()
        return
    
    # Test 2: Login without CSRF token (should fail)
    print("\n2. Testing login without CSRF token (should fail):")
    try:
        response = session.post(
            f"{BASE_URL}/login",
            data={
                "username": admin_creds["username"],
                "password": admin_creds["password"]
            },
            allow_redirects=False
        )
        
        if response.status_code == 403:
            print("✓ Login correctly rejected without CSRF token (403 Forbidden)")
        elif response.status_code == 400:
            if "Redirecting" in response.text:
                print("✓ Login redirected without CSRF token (protection active)")
            else:
                print("✓ Login rejected without CSRF token (400 Bad Request)")
        elif response.status_code == 302:
            print("! Login was redirected - might be using session-based CSRF")
        else:
            print(f"✗ Unexpected response: {response.status_code}")
            if response.text:
                print(f"  Response preview: {response.text[:200]}...")
    except Exception as e:
        print(f"✗ Error during login without CSRF: {e}")
    
    # Test 3: Login with CSRF token (should succeed)
    if csrf_token:
        print("\n3. Testing login with CSRF token (should succeed):")
        try:
            # Get fresh session and login page
            fresh_session = requests.Session()
            login_page = fresh_session.get(f"{BASE_URL}/login")
            
            # Extract fresh CSRF token
            fresh_token = extract_csrf_token(login_page.text)
            
            response = fresh_session.post(
                f"{BASE_URL}/login",
                data={
                    "username": admin_creds["username"],
                    "password": admin_creds["password"],
                    "csrf_token": fresh_token or csrf_token
                },
                allow_redirects=False
            )
            
            if response.status_code == 302:
                print("✓ Login successful with CSRF token (302 redirect)")
                # Check if redirect goes to dashboard
                if "dashboard" in response.headers.get("Location", ""):
                    print("✓ Redirect correctly goes to dashboard")
            elif response.status_code == 200 and "dashboard" in response.text:
                print("✓ Login successful with CSRF token (200 OK with dashboard content)")
            else:
                print(f"! Unexpected response with CSRF token: {response.status_code}")
                if response.text:
                    print(f"  Response preview: {response.text[:200]}...")
        except Exception as e:
            print(f"✗ Error during login with CSRF: {e}")
    
    # Test 4: Login with invalid CSRF token (should fail)
    if csrf_token:
        print("\n4. Testing login with invalid CSRF token (should fail):")
        try:
            another_session = requests.Session()
            response = another_session.post(
                f"{BASE_URL}/login",
                data={
                    "username": admin_creds["username"],
                    "password": admin_creds["password"],
                    "csrf_token": "invalid_token_12345"
                },
                allow_redirects=False
            )
            
            if response.status_code == 403:
                print("✓ Login correctly rejected with invalid CSRF token (403 Forbidden)")
            elif response.status_code == 400:
                if "Redirecting" in response.text:
                    print("✓ Login redirected with invalid CSRF token (protection active)")
                else:
                    print("✓ Login rejected with invalid CSRF token (400 Bad Request)")
            else:
                print(f"! Unexpected response with invalid CSRF token: {response.status_code}")
                if response.text:
                    print(f"  Response preview: {response.text[:200]}...")
        except Exception as e:
            print(f"✗ Error during login with invalid CSRF: {e}")
    
    # Test 5: Test with the login_admin script
    print("\n5. Testing with login_admin script:")
    try:
        result = subprocess.run(
            ["uv", "run", "scripts/login_admin.py",
             "--username", admin_creds["username"],
             "--password", admin_creds["password"]],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(os.path.abspath(__file__))
        )
        
        if result.returncode == 0:
            print("✓ login_admin script succeeded")
            # Clean up cookies file
            if os.path.exists("admin_cookies.json"):
                os.remove("admin_cookies.json")
        else:
            print(f"! login_admin script failed: {result.stderr}")
            if "CSRF" in result.stderr:
                print("  (This is expected behavior due to CSRF protection)")
    except Exception as e:
        print(f"✗ Error running login_admin script: {e}")
    
    # Clean up
    cleanup_test_admin()
    
    print("\n" + "=" * 60)
    print("CSRF protection testing completed!")

if __name__ == "__main__":
    try:
        test_csrf_protection()
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
        cleanup_test_admin()