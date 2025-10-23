#!/usr/bin/env python3
"""
Test script to verify the rate limiter fix for the RequestLimit description attribute error.
"""

import requests
import time
import json

def test_rate_limit():
    """Test the rate limit endpoint to verify the fix works."""
    base_url = "http://127.0.0.1:5000"
    
    print("Testing rate limiter fix...")
    print("=" * 50)
    
    # Test the test-rate-limit endpoint which has a 5 per minute limit
    endpoint = f"{base_url}/test-rate-limit"
    
    print(f"Testing endpoint: {endpoint}")
    print("This endpoint has a limit of 5 requests per minute.")
    print()
    
    # Make 6 requests to trigger the rate limit
    for i in range(1, 7):
        try:
            response = requests.get(endpoint)
            print(f"Request {i}: Status Code: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"  Response: {data}")
            elif response.status_code == 429:
                print("  Rate limit exceeded!")
                try:
                    data = response.json()
                    print(f"  Error Response: {json.dumps(data, indent=2)}")
                except:
                    print(f"  HTML Response: {response.text[:200]}...")
                
                # Check if the error contains our expected error message
                if "Rate limit exceeded" in response.text:
                    print("  ✓ Rate limit error message is correct!")
                else:
                    print("  ✗ Rate limit error message is unexpected!")
                
                # Test passed - we got a 429 without the AttributeError
                print("\n✓ Test PASSED: Rate limiter is working correctly without AttributeError!")
                return True
            else:
                print(f"  Unexpected status code: {response.status_code}")
                
        except requests.exceptions.ConnectionError:
            print(f"Request {i}: Connection failed - make sure the app is running on {base_url}")
            return False
        except Exception as e:
            print(f"Request {i}: Error: {e}")
            return False
        
        # Small delay between requests
        time.sleep(0.5)
    
    print("\n✗ Test FAILED: Rate limit was not triggered after 6 requests")
    return False

if __name__ == "__main__":
    print("Starting rate limiter test...")
    print("Make sure the Flask app is running with: uv run app.py")
    print()
    
    success = test_rate_limit()
    
    if success:
        print("\n" + "=" * 50)
        print("SUCCESS: The rate limiter fix is working correctly!")
        print("The 'RequestLimit' object has no attribute 'description' error is resolved.")
    else:
        print("\n" + "=" * 50)
        print("FAILURE: The test could not verify the fix.")
        print("Please ensure the Flask app is running and try again.")