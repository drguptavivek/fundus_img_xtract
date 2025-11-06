#!/usr/bin/env python3
"""
Script to login as admin user and save session cookies for testing
"""

import sys
import json
import requests
from pathlib import Path
import argparse
import os
from utils.env_loader import load_environment
load_environment()

# Add the project root to the path
file_path = Path(__file__).resolve()
project_root = file_path.parent.parent
sys.path.insert(0, str(project_root))

def login_admin(username="Test", password="test@123", base_url=None, output_file="admin_cookies.json"):
    """Login as admin and save session cookies"""
    
    # Use BASE_URL from environment if not provided
    if base_url is None:
        base_url = os.getenv("BASE_URL", "http://127.0.0.1:5001")
    """Login as admin and save session cookies"""
    
    # Create a session to maintain cookies
    session = requests.Session()
    
    # First, get the login page to obtain CSRF token
    try:
        login_page = session.get(f"{base_url}/login")
        if login_page.status_code != 200:
            print(f"Failed to access login page: {login_page.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print(f"Could not connect to {base_url}. Make sure the application is running.")
        return False
    
    # Extract CSRF token from the login page
    csrf_token = None
    if 'csrf_token' in session.cookies:
        csrf_token = session.cookies['csrf_token']
    
    # Prepare login data with CSRF token if available
    login_data = {
        "username": username,
        "password": password
    }
    
    if csrf_token:
        login_data["csrf_token"] = csrf_token
    
    # Attempt to login
    try:
        response = session.post(
            f"{base_url}/login",
            data=login_data,
            headers={"Referer": f"{base_url}/login"}
        )
    except requests.exceptions.ConnectionError:
        print(f"Could not connect to {base_url}. Make sure the application is running.")
        return False
    
    # Check if login was successful
    if response.status_code == 200 and "dashboard" in response.url:
        print(f"Successfully logged in as {username}")
        
        # Save cookies to file
        cookies_dict = dict(session.cookies)
        try:
            with open(output_file, 'w') as f:
                json.dump(cookies_dict, f, indent=2)
            print(f"Session cookies saved to {output_file}")
            return True
        except Exception as e:
            print(f"Failed to save cookies: {e}")
            return False
    else:
        print(f"Login failed. Status code: {response.status_code}")
        if response.status_code == 403:
            print("Login blocked by CSRF protection or rate limiting")
        elif response.status_code == 401:
            print("Invalid credentials")
        return False

def main():
    parser = argparse.ArgumentParser(description="Login as admin and save session cookies")
    parser.add_argument("--username", default="Test", help="Admin username (default: Test)")
    parser.add_argument("--password", default="test@123", help="Admin password (default: test@123)")
    parser.add_argument("--base-url", default=None, help="Base URL of the application (defaults to BASE_URL from env)")
    parser.add_argument("--output", default="admin_cookies.json", help="Output file for cookies")
    
    args = parser.parse_args()
    
    success = login_admin(
        username=args.username,
        password=args.password,
        base_url=args.base_url,
        output_file=args.output
    )
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()