#!/usr/bin/env python3
"""
Test script for KPI API endpoints with authentication
"""
import requests
import json
from bs4 import BeautifulSoup

# Base URL for API
BASE_URL = "http://127.0.0.1:5001/api/kpis/encounter-files"

def login_and_get_session():
    """Login to get session cookie."""
    # Use existing session cookie from previous login
    session_cookie = "d48a3fe7fb2fc37d6f8fc0b24e81c94ce06e5ee5cea0a322c980c4dd65d9fdd2"
    print(f"✅ Using existing session cookie: {session_cookie}")
    return session_cookie

def test_endpoint(endpoint_name, session_cookie):
    """Test a specific endpoint and return response."""
    url = f"{BASE_URL}/{endpoint_name}"
    headers = {"Cookie": f"session={session_cookie}"}
    
    print(f"\n=== Testing {endpoint_name} ===")
    print(f"URL: {url}")
    
    try:
        response = requests.get(url, headers=headers)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("✅ SUCCESS")
            print(f"Response keys: {list(data.keys())}")
            if 'data' in data:
                print(f"Data keys: {list(data['data'].keys())}")
        else:
            print("❌ FAILED")
            print(f"Response: {response.text}")
            
    except Exception as e:
        print(f"❌ ERROR: {e}")
    
    return response.status_code == 200

def main():
    """Test all KPI endpoints."""
    # Login first
    session_cookie = login_and_get_session()
    if not session_cookie:
        print("❌ Cannot proceed without login")
        return
    
    endpoints = [
        "year-month-wise-uploads",
        "dr-reports-count",
        "glaucoma-reports-count",
        "images-count",
        "dr-results-distribution",
        "glaucoma-results-distribution",
        "vcdr-distribution",
        "processing-times",
        "lab-unit-performance"
    ]
    
    results = {}
    for endpoint in endpoints:
        results[endpoint] = test_endpoint(endpoint, session_cookie)
    
    print("\n=== SUMMARY ===")
    for endpoint, success in results.items():
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{endpoint}: {status}")
    
    total_passed = sum(results.values())
    total_tests = len(results)
    print(f"\nTotal: {total_passed}/{total_tests} endpoints working")

if __name__ == "__main__":
    main()