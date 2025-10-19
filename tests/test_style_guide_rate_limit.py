#!/usr/bin/env python3
"""
Test script to verify rate limiting functionality on the style_guide route.
"""

import os
import requests
import time
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Base URL of the application from environment variable
BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:5001")

def test_rate_limiter():
    """Test the rate limiter by making multiple requests to the style_guide endpoint."""
    print("Testing rate limiter on /style_guide route...")
    print(f"Making requests to {BASE_URL}/style_guide")
    print("-" * 50)
    
    # Make 105 requests to the style_guide endpoint (limit is 100 per minute)
    for i in range(1, 106):
        try:
            # Make a GET request to style_guide
            response = requests.get(f"{BASE_URL}/style_guide")
            
            print(f"Request {i}: Status Code: {response.status_code}")
            
            # Check for rate limit headers
            if 'X-RateLimit-Limit' in response.headers:
                print(f"  X-RateLimit-Limit: {response.headers['X-RateLimit-Limit']}")
            if 'X-RateLimit-Remaining' in response.headers:
                print(f"  X-RateLimit-Remaining: {response.headers['X-RateLimit-Remaining']}")
            if 'X-RateLimit-Reset' in response.headers:
                print(f"  X-RateLimit-Reset: {response.headers['X-RateLimit-Reset']}")
            
            # Check response content
            if response.status_code == 200:
                print(f"  Response: OK (Content-Length: {len(response.content)} bytes)")
            elif response.status_code == 429:
                print("  Rate limit exceeded!")
                if 'retry-after' in response.headers:
                    print(f"  Retry-After: {response.headers['retry-after']}")
                # Check if there's a flash message in the content
                if 'Rate limit exceeded' in response.text:
                    print("  Flash message found in response")
                # Once we hit rate limit, we can stop
                break
            else:
                print(f"  Unexpected status code")
                
        except requests.exceptions.ConnectionError:
            print(f"Request {i}: Connection error - is the app running?")
            sys.exit(1)
        except Exception as e:
            print(f"Request {i}: Error: {e}")
            
        # Small delay between requests
        if i < 106:
            time.sleep(0.1)
    
    print("-" * 50)
    print("Rate limiter test completed.")

if __name__ == "__main__":
    test_rate_limiter()