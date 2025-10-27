"""
Example script demonstrating how to use the authentication helpers.

This script shows how to use the test_auth_helpers module to authenticate
as test users and make authenticated requests to the application.
"""

from test_auth_helpers import login_as_test_admin, login_as_test_manager, make_authenticated_request
import os

def main():
    """Example usage of authentication helpers."""
    
    # Get base URL from environment
    base_url = os.getenv('BASE_URL', 'http://127.0.0.1:5001')
    
    print("=== Authentication Helper Example ===\n")
    
    try:
        # Login as test_admin
        print("1. Logging in as test_admin...")
        admin_cookies = login_as_test_admin()
        print("   ✓ Admin login successful!")
        print(f"   Cookies received: {list(admin_cookies.keys())}")
        
        # Make an authenticated request as admin
        print("\n2. Making authenticated request as admin...")
        response = make_authenticated_request(f"{base_url}/dashboard", admin_cookies)
        print(f"   Dashboard response status: {response.status_code}")
        
        # Login as test_manager
        print("\n3. Logging in as test_manager...")
        manager_cookies = login_as_test_manager()
        print("   ✓ Manager login successful!")
        print(f"   Cookies received: {list(manager_cookies.keys())}")
        
        # Make an authenticated request as manager
        print("\n4. Making authenticated request as manager...")
        response = make_authenticated_request(f"{base_url}/dashboard", manager_cookies)
        print(f"   Dashboard response status: {response.status_code}")
        
        print("\n=== Example completed successfully! ===")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())