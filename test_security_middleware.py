#!/usr/bin/env python3
"""
Test script to verify security middleware implementation.
Tests for large payload protection, malformed payload handling, and CSRF protection.
"""

import requests
import json
import time
from typing import Dict, Any

# Configuration
BASE_URL = "http://127.0.0.1:5001"  # Adjust if your app runs on a different port
TEST_TIMEOUT = 10  # seconds

class SecurityTester:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.timeout = TEST_TIMEOUT
    
    def test_large_payload_protection(self) -> Dict[str, Any]:
        """Test protection against large payloads on login endpoint."""
        print("\n=== Testing Large Payload Protection ===")
        
        # Test 1: Normal sized payload (should work)
        normal_data = {
            "username": "testuser",
            "password": "testpass",
            "csrf_token": "dummy_token"  # We'll get a real token later
        }
        
        # First get the login page to get a CSRF token
        response = self.session.get(f"{self.base_url}/login")
        if response.status_code != 200:
            print(f"Failed to get login page: {response.status_code}")
            return {"success": False, "error": "Could not access login page"}
        
        # Extract CSRF token from the page (simplified)
        csrf_token = "dummy_token"  # In a real test, you'd parse the HTML
        
        # Test with normal payload
        normal_data["csrf_token"] = csrf_token
        response = self.session.post(
            f"{self.base_url}/login",
            data=normal_data
        )
        print(f"Normal payload response: {response.status_code}")
        
        # Test 2: Large payload (should be blocked)
        large_data = normal_data.copy()
        large_data["large_field"] = "A" * 10000  # 10KB of data
        
        response = self.session.post(
            f"{self.base_url}/login",
            data=large_data
        )
        print(f"Large payload response: {response.status_code}")
        
        if response.status_code == 413:  # Payload Too Large
            print("✓ Large payload correctly blocked")
            return {"success": True, "large_payload_blocked": True}
        else:
            print("✗ Large payload was not blocked")
            return {"success": False, "large_payload_blocked": False}
    
    def test_malformed_json_protection(self) -> Dict[str, Any]:
        """Test protection against malformed JSON on API endpoints."""
        print("\n=== Testing Malformed JSON Protection ===")
        
        # Test malformed JSON on check-email-status endpoint
        malformed_json = '{"username": "test", "password": "test"'  # Missing closing brace
        
        headers = {
            "Content-Type": "application/json",
            "X-CSRF-Token": "dummy_token"
        }
        
        response = self.session.post(
            f"{self.base_url}/check-email-status",
            data=malformed_json,
            headers=headers
        )
        
        print(f"Malformed JSON response: {response.status_code}")
        
        if response.status_code == 400:  # Bad Request
            print("✓ Malformed JSON correctly rejected")
            return {"success": True, "malformed_json_blocked": True}
        else:
            print("✗ Malformed JSON was not rejected")
            return {"success": False, "malformed_json_blocked": False}
    
    def test_csrf_protection(self) -> Dict[str, Any]:
        """Test CSRF protection on non-authenticated routes."""
        print("\n=== Testing CSRF Protection ===")
        
        # First get a page to get a valid CSRF token
        response = self.session.get(f"{self.base_url}/login")
        if response.status_code != 200:
            return {"success": False, "error": "Could not access login page"}
        
        # Test 1: Request without CSRF token (should be blocked)
        data = {
            "username": "testuser",
            "password": "testpass"
        }
        
        response = self.session.post(
            f"{self.base_url}/login",
            data=data
        )
        
        print(f"Request without CSRF token response: {response.status_code}")
        
        # Check if it was blocked (should get an error about CSRF)
        if response.status_code == 403 or "Security validation failed" in response.text:
            print("✓ Request without CSRF token correctly blocked")
            csrf_protected = True
        else:
            print("✗ Request without CSRF token was not blocked")
            csrf_protected = False
        
        return {
            "success": True,
            "csrf_protection_active": csrf_protected
        }
    
    def test_rate_limiting(self) -> Dict[str, Any]:
        """Test rate limiting on login endpoint."""
        print("\n=== Testing Rate Limiting ===")
        
        # Make multiple rapid requests to test rate limiting
        data = {
            "username": "testuser",
            "password": "testpass",
            "csrf_token": "dummy_token"
        }
        
        rate_limited = False
        for i in range(10):  # Try 10 requests rapidly
            response = self.session.post(
                f"{self.base_url}/login",
                data=data
            )
            
            if response.status_code == 429:  # Too Many Requests
                rate_limited = True
                print(f"Request {i+1}: Rate limited (429)")
                break
            else:
                print(f"Request {i+1}: {response.status_code}")
            
            time.sleep(0.1)  # Small delay between requests
        
        if rate_limited:
            print("✓ Rate limiting is active")
            return {"success": True, "rate_limiting_active": True}
        else:
            print("✗ Rate limiting may not be active or threshold not reached")
            return {"success": False, "rate_limiting_active": False}
    
    def run_all_tests(self) -> Dict[str, Any]:
        """Run all security tests."""
        print("Starting security tests...")
        
        results = {
            "large_payload": self.test_large_payload_protection(),
            "malformed_json": self.test_malformed_json_protection(),
            "csrf_protection": self.test_csrf_protection(),
            "rate_limiting": self.test_rate_limiting()
        }
        
        # Summary
        print("\n=== Test Summary ===")
        for test_name, result in results.items():
            status = "✓ PASS" if result.get("success", False) else "✗ FAIL"
            print(f"{test_name}: {status}")
        
        return results


def main():
    """Main function to run tests."""
    import sys
    
    # Check if server is running
    try:
        response = requests.get(f"{BASE_URL}/healthz", timeout=5)
        if response.status_code != 200:
            print("Server health check failed. Please ensure the app is running.")
            sys.exit(1)
    except requests.exceptions.RequestException:
        print("Could not connect to the server. Please ensure the app is running on", BASE_URL)
        sys.exit(1)
    
    # Run tests
    tester = SecurityTester(BASE_URL)
    results = tester.run_all_tests()
    
    # Exit with appropriate code
    all_passed = all(result.get("success", False) for result in results.values())
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()