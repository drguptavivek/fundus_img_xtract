#!/usr/bin/env python3
"""
Test invalid UUID submission with proper CSRF token.
"""

import requests
import json
from bs4 import BeautifulSoup

BASE_URL = "http://127.0.0.1:5001"
USERNAME = "test2ComophArbit"
PASSWORD = "Vivek@2026"

def login(session):
    """Login to the application."""
    login_url = f"{BASE_URL}/login"
    
    # Get login page to extract CSRF token
    response = session.get(login_url)
    soup = BeautifulSoup(response.text, 'html.parser')
    csrf_input = soup.find('input', {'name': 'csrf_token'})
    csrf_token = csrf_input['value'] if csrf_input else None
    
    # Submit login form
    login_data = {
        'username': USERNAME,
        'password': PASSWORD,
        'csrf_token': csrf_token
    }
    
    response = session.post(login_url, data=login_data, allow_redirects=False)
    return response.status_code in [302, 303]

def get_csrf_token(session, url):
    """Get CSRF token from a page."""
    response = session.get(url)
    if response.status_code != 200:
        return None
    
    soup = BeautifulSoup(response.text, 'html.parser')
    csrf_input = soup.find('input', {'name': 'csrf_token'})
    return csrf_input['value'] if csrf_input else None

def test_invalid_uuid_with_csrf(session):
    """Test submitting form with invalid UUID but valid CSRF."""
    print("\n=== Testing Invalid UUID with Valid CSRF ===")
    
    # Get CSRF token from a valid page first
    csrf_token = get_csrf_token(session, f"{BASE_URL}/grading/intra-task/5a372b5e-ee3d-46ee-88f7-64e81dbf370c")
    
    if not csrf_token:
        print("❌ Could not get CSRF token")
        return False
    
    # Submit with invalid UUID
    submit_url = f"{BASE_URL}/grading/intra-task/submit"
    
    form_data = {
        'task_uuid': 'invalid-uuid-format',
        'label_id': 1,
        'comment': 'Test with invalid UUID',
        'action': 'save_close',
        'csrf_token': csrf_token
    }
    
    response = session.post(submit_url, data=form_data, allow_redirects=False)
    
    print(f"Status code: {response.status_code}")
    
    if response.status_code == 302:
        location = response.headers.get('Location', '')
        if '/grading' in location:
            print("✅ Invalid UUID correctly rejected - redirected to grading index")
            return True
        else:
            print(f"❌ Unexpected redirect: {location}")
            return False
    else:
        print(f"❌ Invalid UUID submission failed with status: {response.status_code}")
        return False

def main():
    session = requests.Session()
    
    # Login first
    if not login(session):
        print("Login failed")
        return
    
    # Test invalid UUID with valid CSRF
    test_invalid_uuid_with_csrf(session)

if __name__ == "__main__":
    main()