#!/usr/bin/env python3
"""
Test script for KPI API endpoints with authentication
"""
import requests
import json
from bs4 import BeautifulSoup
import os
import sys
# Load environment variables
from utils.env_loader import load_environment
load_environment()

# Add the parent directory to the path to import test_auth_helpers
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_auth_helpers import login_as_test_admin, make_authenticated_request

# Base URL for API
BASE_URL = f"{os.getenv('BASE_URL', 'http://127.0.0.1:5001')}/api/kpis/encounter-files"

def login_and_get_session():
    """Login to get session cookie using authentication helper."""
    try:
        cookies = login_as_test_admin()
        print("✅ Successfully logged in as test_admin")
        return cookies
    except Exception as e:
        print(f"❌ Login failed: {e}")
        return None

def test_endpoint(endpoint_name, cookies):
    """Test a specific endpoint and return response."""
    url = f"{BASE_URL}/{endpoint_name}"
    
    print(f"\n=== Testing {endpoint_name} ===")
    print(f"URL: {url}")
    
    try:
        response = make_authenticated_request(url, cookies)
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
    cookies = login_and_get_session()
    if not cookies:
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
        results[endpoint] = test_endpoint(endpoint, cookies)
    
    print("\n=== SUMMARY ===")
    for endpoint, success in results.items():
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{endpoint}: {status}")
    
    total_passed = sum(results.values())
    total_tests = len(results)
    print(f"\nTotal: {total_passed}/{total_tests} endpoints working")

if __name__ == "__main__":
    main()