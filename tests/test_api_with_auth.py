"""
Example test script showing how to use authentication helpers to test API endpoints.

This script demonstrates how other Python scripts can import and use the
authentication helpers to make authenticated requests to the application.
"""

import sys
import os
# Add the parent directory to the path to import test_auth_helpers
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_auth_helpers import login_as_test_admin, login_as_test_manager, make_authenticated_request
import json

def test_admin_endpoints():
    """Test admin-specific endpoints using authentication helpers."""
    
    base_url = os.getenv('BASE_URL', 'http://127.0.0.1:5001')
    
    print("Testing admin endpoints with authentication...")
    
    try:
        # Login as admin
        admin_cookies = login_as_test_admin()
        print("✓ Admin login successful")
        
        # Test admin dashboard
        response = make_authenticated_request(f"{base_url}/dashboard", admin_cookies)
        print(f"✓ Dashboard endpoint: {response.status_code}")
        
        # Test admin analytics endpoint (if exists)
        response = make_authenticated_request(f"{base_url}/analytics", admin_cookies)
        print(f"✓ Analytics endpoint: {response.status_code}")
        
        # Test API endpoint with JSON data
        api_url = f"{base_url}/api/hospitals"
        response = make_authenticated_request(api_url, admin_cookies, method='GET')
        print(f"✓ Hospitals API endpoint: {response.status_code}")
        
        if response.status_code == 200:
            try:
                data = response.json()
                print(f"  Response contains {len(data)} hospitals")
            except:
                print("  Response is not JSON")
        
        return True
        
    except Exception as e:
        print(f"❌ Admin endpoint test failed: {e}")
        return False

def test_manager_endpoints():
    """Test manager-specific endpoints using authentication helpers."""
    
    base_url = os.getenv('BASE_URL', 'http://127.0.0.1:5001')
    
    print("\nTesting manager endpoints with authentication...")
    
    try:
        # Login as manager
        manager_cookies = login_as_test_manager()
        print("✓ Manager login successful")
        
        # Test manager dashboard
        response = make_authenticated_request(f"{base_url}/dashboard", manager_cookies)
        print(f"✓ Dashboard endpoint: {response.status_code}")
        
        # Test screenings endpoint
        response = make_authenticated_request(f"{base_url}/screenings", manager_cookies)
        print(f"✓ Screenings endpoint: {response.status_code}")
        
        return True
        
    except Exception as e:
        print(f"❌ Manager endpoint test failed: {e}")
        return False

def main():
    """Run all authentication tests."""
    
    print("=== API Authentication Test ===\n")
    
    admin_success = test_admin_endpoints()
    manager_success = test_manager_endpoints()
    
    if admin_success and manager_success:
        print("\n✅ All authentication tests passed!")
        return 0
    else:
        print("\n❌ Some tests failed!")
        return 1

if __name__ == "__main__":
    exit(main())