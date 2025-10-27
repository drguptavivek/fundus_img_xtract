#!/usr/bin/env python3
"""
Script to save login cookies for API testing
Usage: python script_login_save_cookie.py username password
"""

import sys
import requests
import json

def main():
    if len(sys.argv) != 3:
        print("Usage: python script_login_save_cookie.py username password")
        sys.exit(1)
    
    username = sys.argv[1]
    password = sys.argv[2]
    
    # Login URL
    login_url = "http://127.0.0.1:5001/login"
    
    # Create session
    session = requests.Session()
    
    # Get login page first to get CSRF token
    login_page = session.get(login_url)
    
    # Extract CSRF token from the page (from cookies or form)
    csrf_token = None
    if 'csrf_token' in login_page.cookies:
        csrf_token = login_page.cookies['csrf_token']
    else:
        # Try to extract from form content
        import re
        csrf_match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', login_page.text)
        if csrf_match:
            csrf_token = csrf_match.group(1)
    
    # Login data
    login_data = {
        'username': username,
        'password': password,
        'remember': False
    }
    
    if csrf_token:
        login_data['csrf_token'] = csrf_token
    
    # Post login
    response = session.post(login_url, data=login_data)
    
    if response.status_code == 200:
        # Save cookies to file
        cookies = session.cookies.get_dict()
        
        with open('test_cookies.json', 'w') as f:
            json.dump(cookies, f)
        
        print("Login successful! Cookies saved to test_cookies.json")
        print(f"Session cookie: {cookies.get('session', 'Not found')}")
    else:
        print(f"Login failed with status code: {response.status_code}")
        print(f"Response: {response.text}")

if __name__ == "__main__":
    main()