#!/usr/bin/env python3
"""
Test script to verify images-count endpoint works without NaT error
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from tests.test_auth_helpers import login_as_test_admin, make_authenticated_request

def test_images_count_api():
    """Test that images-count endpoint works without NaT errors"""
    
    print("=== Testing images-count API Endpoint ===")
    
    # Login as admin
    print("1. Logging in as test_admin...")
    admin_cookies = login_as_test_admin()
    
    if not admin_cookies:
        print("✗ Admin login failed!")
        return False
    
    print("✓ Admin login successful!")
    
    # Test the originally failing endpoint
    print("\n2. Testing /api/kpis/encounter-files/images-count...")
    url = "http://127.0.0.1:5001/api/kpis/encounter-files/images-count"
    
    try:
        response = make_authenticated_request(url, admin_cookies)
        
        if response.status_code == 200:
            print("✓ API call successful (status 200)")
            
            # Try to parse JSON to ensure it's valid
            try:
                import json
                data = response.json()
                if data.get('success'):
                    print("✓ JSON response is valid and success=True")
                    total_encounters = data.get('data', {}).get('total_encounters', 0)
                    verified_images = data.get('data', {}).get('verified_images', 0)
                    verification_rate = data.get('data', {}).get('verification_rate', 0)
                    print(f"✓ Response data: {total_encounters} encounters, {verified_images} verified, {verification_rate}% rate")
                    return True
                else:
                    print(f"✗ API returned success=False: {data.get('message', 'Unknown error')}")
                    return False
            except json.JSONDecodeError as e:
                print(f"✗ JSON parsing failed: {e}")
                return False
        else:
            print(f"✗ API call failed with status {response.status_code}")
            print(f"Response: {response.text[:200]}...")
            return False
            
    except Exception as e:
        print(f"✗ Request failed with exception: {e}")
        return False

if __name__ == "__main__":
    success = test_images_count_api()
    if success:
        print("\n=== images-count API Test PASSED ===")
        sys.exit(0)
    else:
        print("\n=== images-count API Test FAILED ===")
        sys.exit(1)