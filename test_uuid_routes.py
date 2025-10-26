#!/usr/bin/env python3
"""
Test script for UUID implementation in intra-rater tasks.
"""

import requests
import re
from bs4 import BeautifulSoup

BASE_URL = "http://127.0.0.1:5001"
USERNAME = "test2ComophArbit"
PASSWORD = "Vivek@2026"

def login(session):
    """Login to the application."""
    login_url = f"{BASE_URL}/login"
    
    # Get the login page to extract CSRF token
    response = session.get(login_url)
    if response.status_code != 200:
        print(f"Failed to get login page: {response.status_code}")
        return False
    
    # Extract CSRF token
    soup = BeautifulSoup(response.text, 'html.parser')
    csrf_input = soup.find('input', {'name': 'csrf_token'})
    csrf_token = csrf_input['value'] if csrf_input else None
    
    if not csrf_token:
        print("Could not find CSRF token in login page")
        return False
    
    # Submit login form
    login_data = {
        'username': USERNAME,
        'password': PASSWORD,
        'csrf_token': csrf_token
    }
    
    response = session.post(login_url, data=login_data, allow_redirects=False)
    
    # Check if login was successful (redirect to home page)
    if response.status_code in [302, 303]:
        print("Login successful!")
        return True
    else:
        print(f"Login failed with status code: {response.status_code}")
        print(f"Response: {response.text[:500]}")
        return False

def test_valid_uuid(session, uuid):
    """Test accessing an intra-rater task with a valid UUID."""
    url = f"{BASE_URL}/grading/intra-task/{uuid}"
    response = session.get(url, allow_redirects=False)
    
    print(f"\nTesting valid UUID: {uuid}")
    print(f"Status code: {response.status_code}")
    
    if response.status_code == 200:
        print("✅ Successfully accessed intra-rater task with valid UUID")
        return True
    elif response.status_code == 302:
        # Check if it's redirecting to login (not logged in) or back to grading index
        location = response.headers.get('Location', '')
        if '/login' in location:
            print("❌ Redirected to login - authentication issue")
        elif '/grading' in location:
            print("❌ Redirected to grading index - task not found or not authorized")
        else:
            print(f"❌ Redirected to: {location}")
        return False
    else:
        print(f"❌ Unexpected response: {response.text[:200]}")
        return False

def test_invalid_uuid(session, uuid):
    """Test accessing an intra-rater task with an invalid UUID."""
    url = f"{BASE_URL}/grading/intra-task/{uuid}"
    response = session.get(url, allow_redirects=False)
    
    print(f"\nTesting invalid UUID: {uuid}")
    print(f"Status code: {response.status_code}")
    
    if response.status_code == 302:
        # Should redirect to grading index with flash message
        location = response.headers.get('Location', '')
        if '/grading' in location:
            print("✅ Correctly redirected to grading index for invalid UUID")
            return True
        else:
            print(f"❌ Unexpected redirect for invalid UUID: {location}")
            return False
    else:
        print(f"❌ Unexpected response for invalid UUID: {response.status_code}")
        return False

def main():
    session = requests.Session()
    
    # Login first
    if not login(session):
        return
    
    # Test with valid UUIDs from database
    valid_uuids = [
        "5a372b5e-ee3d-46ee-88f7-64e81dbf370c",  # New test task for our user
        "f2a5775e-1c98-4578-a97f-1e990998c9b6",  # Existing task for different user
        "ea652d38-1bb7-444c-a493-4910f87ba99b"
    ]
    
    # Test with invalid UUID formats
    invalid_uuids = [
        "invalid-uuid-format",
        "123-456-789",
        "not-a-uuid-at-all",
        "f2a5775e-1c98-4578-a97f-1e990998c9b",  # Missing one character
        "f2a5775e-1c98-4578-a97f-1e990998c9b66",  # Extra character
        ""  # Empty UUID
    ]
    
    print("=== Testing Valid UUIDs ===")
    for uuid in valid_uuids:
        test_valid_uuid(session, uuid)
    
    print("\n=== Testing Invalid UUIDs ===")
    for uuid in invalid_uuids:
        test_invalid_uuid(session, uuid)

if __name__ == "__main__":
    main()