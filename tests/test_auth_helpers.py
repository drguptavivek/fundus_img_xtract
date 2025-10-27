"""
Authentication helper functions for testing.

This module provides functions to authenticate as test users and retrieve
session cookies that can be used for making authenticated requests to
the application endpoints during testing.
"""

import os
import re
import requests
from dotenv import load_dotenv
from typing import Dict, Optional

# Load environment variables from .env.testing for test credentials
# Use absolute path from project root
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env.testing'))
# Also load .env for BASE_URL
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))


def get_csrf_token(session: requests.Session, base_url: str) -> Optional[str]:
    """
    Extract CSRF token from the login page.
    
    Args:
        session: The requests session object
        base_url: Base URL of the application
        
    Returns:
        CSRF token string or None if not found
    """
    try:
        # Get the login page to extract CSRF token
        response = session.get(f"{base_url}/login")
        response.raise_for_status()
        
        # Extract CSRF token from the HTML
        # The token is typically in a hidden input field with name="csrf_token"
        csrf_match = re.search(r'name="csrf_token"\s+type="hidden"\s+value="([^"]+)"', response.text)
        if csrf_match:
            return csrf_match.group(1)
        
        # Alternative pattern for different HTML structures
        csrf_match = re.search(r'<input[^>]*name="csrf_token"[^>]*value="([^"]+)"', response.text)
        if csrf_match:
            return csrf_match.group(1)
            
        return None
    except Exception as e:
        print(f"Error getting CSRF token: {e}")
        return None


def login_as_test_admin(base_url: Optional[str] = None) -> Dict[str, str]:
    """
    Log in as test_admin user and return session cookies.
    
    Args:
        base_url: Base URL of the application (optional, defaults to BASE_URL from .env)
        
    Returns:
        Dictionary containing session cookies for authenticated requests
        
    Raises:
        Exception: If login fails or credentials are not found
    """
    # Use provided base_url or get from environment
    if base_url is None:
        base_url = os.getenv('BASE_URL', 'http://127.0.0.1:5001')
    
    # Get test admin credentials from environment
    username = os.getenv('test_admin')
    password = os.getenv('test_admin_password')
    
    if not username or not password:
        raise Exception("test_admin credentials not found in .env.testing file")
    
    # Create a session to maintain cookies
    session = requests.Session()
    
    # Get CSRF token
    csrf_token = get_csrf_token(session, base_url)
    if not csrf_token:
        raise Exception("Could not retrieve CSRF token from login page")
    
    # Prepare login data
    login_data = {
        'username': username,
        'password': password,
        'csrf_token': csrf_token
    }
    
    try:
        # Make login request
        response = session.post(f"{base_url}/login", data=login_data)
        response.raise_for_status()
        
        # Check if login was successful (redirect or success indicator)
        if response.status_code in [200, 302]:
            # Return the session cookies
            return session.cookies.get_dict()
        else:
            raise Exception(f"Login failed with status code: {response.status_code}")
            
    except requests.exceptions.RequestException as e:
        raise Exception(f"Login request failed: {e}")


def login_as_test_manager(base_url: Optional[str] = None) -> Dict[str, str]:
    """
    Log in as test_manager user and return session cookies.
    
    Args:
        base_url: Base URL of the application (optional, defaults to BASE_URL from .env)
        
    Returns:
        Dictionary containing session cookies for authenticated requests
        
    Raises:
        Exception: If login fails or credentials are not found
    """
    # Use provided base_url or get from environment
    if base_url is None:
        base_url = os.getenv('BASE_URL', 'http://127.0.0.1:5001')
    
    # Get test manager credentials from environment
    username = os.getenv('test_manager')
    password = os.getenv('test_manager_password')
    
    if not username or not password:
        raise Exception("test_manager credentials not found in .env.testing file")
    
    # Create a session to maintain cookies
    session = requests.Session()
    
    # Get CSRF token
    csrf_token = get_csrf_token(session, base_url)
    if not csrf_token:
        raise Exception("Could not retrieve CSRF token from login page")
    
    # Prepare login data
    login_data = {
        'username': username,
        'password': password,
        'csrf_token': csrf_token
    }
    
    try:
        # Make login request
        response = session.post(f"{base_url}/login", data=login_data)
        response.raise_for_status()
        
        # Check if login was successful (redirect or success indicator)
        if response.status_code in [200, 302]:
            # Return the session cookies
            return session.cookies.get_dict()
        else:
            raise Exception(f"Login failed with status code: {response.status_code}")
            
    except requests.exceptions.RequestException as e:
        raise Exception(f"Login request failed: {e}")


def make_authenticated_request(url: str, cookies: Dict[str, str], method: str = 'GET', 
                             data: Optional[Dict] = None, json_data: Optional[Dict] = None) -> requests.Response:
    """
    Make an authenticated request to the application using the provided cookies.
    
    Args:
        url: The endpoint URL
        cookies: Authentication cookies from login functions
        method: HTTP method (GET, POST, PUT, DELETE, etc.)
        data: Form data for POST requests
        json_data: JSON data for POST requests
        
    Returns:
        requests.Response object
    """
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Referer': os.getenv('BASE_URL', 'http://127.0.0.1:5001')
    }
    
    if json_data:
        headers['Content-Type'] = 'application/json'
    
    try:
        if method.upper() == 'GET':
            return requests.get(url, cookies=cookies, headers=headers)
        elif method.upper() == 'POST':
            if json_data:
                return requests.post(url, cookies=cookies, headers=headers, json=json_data)
            else:
                return requests.post(url, cookies=cookies, headers=headers, data=data)
        elif method.upper() == 'PUT':
            if json_data:
                return requests.put(url, cookies=cookies, headers=headers, json=json_data)
            else:
                return requests.put(url, cookies=cookies, headers=headers, data=data)
        elif method.upper() == 'DELETE':
            return requests.delete(url, cookies=cookies, headers=headers)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")
            
    except requests.exceptions.RequestException as e:
        raise Exception(f"Authenticated request failed: {e}")


# Example usage
if __name__ == "__main__":
    try:
        # Example: Login as test_admin
        admin_cookies = login_as_test_admin()
        print("Admin login successful!")
        print(f"Cookies: {admin_cookies}")
        
        # Example: Make an authenticated request
        base_url = os.getenv('BASE_URL', 'http://127.0.0.1:5001')
        response = make_authenticated_request(f"{base_url}/dashboard", admin_cookies)
        print(f"Dashboard response status: {response.status_code}")
        
        # Example: Login as test_manager
        manager_cookies = login_as_test_manager()
        print("Manager login successful!")
        print(f"Cookies: {manager_cookies}")
        
    except Exception as e:
        print(f"Error: {e}")