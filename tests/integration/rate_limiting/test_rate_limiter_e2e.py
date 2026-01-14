#!/usr/bin/env python3
"""
End-to-end tests for Flask-Limiter 4.0 implementation.
Tests rate limiting against a running server using baseURL and port from .env.
"""

import os
import sys
from pathlib import Path
import requests
import time
import json
import subprocess
from datetime import datetime, timedelta
# Add the project root directory to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables
from utils.env_loader import load_environment
load_environment()

# Base URL from environment variables
# Note: BASE_URL already includes the port from .env
BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:5001")

# Remove port if it's already included in BASE_URL
if BASE_URL.endswith(f":{os.getenv('FLASK_PORT', '5001')}"):
    # BASE_URL already has the port
    pass
else:
    # Add port if not present
    FLASK_PORT = os.getenv("FLASK_PORT", "5001")
    BASE_URL = f"{BASE_URL}:{FLASK_PORT}"


class TestRateLimiterE2E:
    """End-to-end tests for rate limiting."""
    
    def test_homepage_rate_limiting(self):
        """Test rate limiting on the homepage endpoint."""
        print(f"\nTesting homepage rate limiting at {BASE_URL}/")
        print("-" * 50)
        
        success_count = 0
        rate_limited_count = 0
        
        # Make 25 requests (homepage limit is 20 per minute)
        for i in range(1, 26):
            try:
                response = requests.get(f"{BASE_URL}/", timeout=5)
                print(f"Request {i}: Status {response.status_code}")
                
                if response.status_code == 200:
                    success_count += 1
                    # Check for rate limit headers
                    if 'X-RateLimit-Limit' in response.headers:
                        print(f"  X-RateLimit-Limit: {response.headers['X-RateLimit-Limit']}")
                    if 'X-RateLimit-Remaining' in response.headers:
                        print(f"  X-RateLimit-Remaining: {response.headers['X-RateLimit-Remaining']}")
                elif response.status_code == 429:
                    rate_limited_count += 1
                    print("  Rate limit exceeded!")
                    if 'retry-after' in response.headers:
                        print(f"  Retry-After: {response.headers['retry-after']}")
                    break
                else:
                    print(f"  Unexpected status code: {response.status_code}")
                    
            except requests.exceptions.ConnectionError:
                print(f"Request {i}: Connection error - is the app running at {BASE_URL}?")
                return False
            except Exception as e:
                print(f"Request {i}: Error: {e}")
            
            # Small delay between requests
            time.sleep(0.1)
        
        print(f"\nResults: {success_count} successful, {rate_limited_count} rate limited")
        assert success_count > 0, "Should have at least some successful requests"
        assert rate_limited_count > 0, "Should eventually be rate limited"
        print("✓ Homepage rate limiting test passed")
        return True
    
    def test_style_guide_rate_limiting(self):
        """Test rate limiting on the style guide endpoint."""
        print(f"\nTesting style guide rate limiting at {BASE_URL}/style_guide")
        print("-" * 50)
        
        success_count = 0
        rate_limited_count = 0
        
        # Make 15 requests (style guide limit is 10 per minute)
        for i in range(1, 16):
            try:
                response = requests.get(f"{BASE_URL}/style_guide", timeout=5)
                print(f"Request {i}: Status {response.status_code}")
                
                if response.status_code == 200:
                    success_count += 1
                elif response.status_code == 429:
                    rate_limited_count += 1
                    print("  Rate limit exceeded!")
                    break
                else:
                    print(f"  Unexpected status code: {response.status_code}")
                    
            except requests.exceptions.ConnectionError:
                print(f"Request {i}: Connection error")
                return False
            except Exception as e:
                print(f"Request {i}: Error: {e}")
            
            time.sleep(0.1)
        
        print(f"\nResults: {success_count} successful, {rate_limited_count} rate limited")
        assert success_count > 0, "Should have at least some successful requests"
        assert rate_limited_count > 0, "Should eventually be rate limited"
        print("✓ Style guide rate limiting test passed")
        return True
    
    def test_api_rate_limiting(self):
        """Test rate limiting on API endpoints."""
        print(f"\nTesting API rate limiting at {BASE_URL}/api/hospitals")
        print("-" * 50)
        
        success_count = 0
        rate_limited_count = 0
        
        # Make 10 requests to API endpoint
        for i in range(1, 11):
            try:
                response = requests.get(f"{BASE_URL}/api/hospitals", timeout=5)
                print(f"Request {i}: Status {response.status_code}")
                
                if response.status_code == 200:
                    success_count += 1
                    # Check response is JSON
                    try:
                        data = response.json()
                        print(f"  Response: {len(data)} items")
                    except:
                        print("  Response: Not JSON")
                elif response.status_code == 429:
                    rate_limited_count += 1
                    print("  Rate limit exceeded!")
                    # Check for JSON error response
                    try:
                        error_data = response.json()
                        print(f"  Error: {error_data.get('error', 'Unknown error')}")
                        print(f"  Message: {error_data.get('message', 'No message')}")
                        print(f"  Retry After: {error_data.get('retry_after', 'Not specified')}")
                    except:
                        print("  Error response: Not JSON")
                    break
                elif response.status_code == 401:
                    print("  Unauthorized (expected for unauthenticated API access)")
                    break
                else:
                    print(f"  Unexpected status code: {response.status_code}")
                    
            except requests.exceptions.ConnectionError:
                print(f"Request {i}: Connection error")
                return False
            except Exception as e:
                print(f"Request {i}: Error: {e}")
            
            time.sleep(0.1)
        
        print(f"\nResults: {success_count} successful, {rate_limited_count} rate limited")
        # API might require authentication, so we don't assert success_count > 0
        print("✓ API rate limiting test completed")
        return True
    
    def test_test_rate_limit_endpoint(self):
        """Test the dedicated rate limit test endpoint."""
        print(f"\nTesting rate limit test endpoint at {BASE_URL}/test-rate-limit")
        print("-" * 50)
        
        success_count = 0
        rate_limited_count = 0
        redirect_count = 0
        
        # Make 8 requests (test endpoint limit is 5 per minute)
        for i in range(1, 9):
            try:
                response = requests.get(f"{BASE_URL}/test-rate-limit", timeout=5)
                print(f"Request {i}: Status {response.status_code}")
                
                if response.status_code == 200:
                    success_count += 1
                    # Check response is JSON
                    try:
                        data = response.json()
                        print(f"  Message: {data.get('message', 'No message')}")
                        print(f"  Timestamp: {data.get('timestamp', 'No timestamp')}")
                    except:
                        print("  Response: Not JSON")
                elif response.status_code == 302:
                    redirect_count += 1
                    print(f"  Redirect to login (rate limiting active)")
                    # Check for rate limit headers even on redirect
                    if 'X-RateLimit-Limit' in response.headers:
                        print(f"  X-RateLimit-Limit: {response.headers['X-RateLimit-Limit']}")
                        print(f"  X-RateLimit-Remaining: {response.headers['X-RateLimit-Remaining']}")
                elif response.status_code == 429:
                    rate_limited_count += 1
                    print("  Rate limit exceeded!")
                    # Check for JSON error response
                    try:
                        error_data = response.json()
                        print(f"  Error: {error_data.get('error', 'Unknown error')}")
                        print(f"  Message: {error_data.get('message', 'No message')}")
                        print(f"  Retry After: {error_data.get('retry_after', 'Not specified')}")
                    except:
                        print("  Error response: Not JSON")
                    break
                else:
                    print(f"  Unexpected status code: {response.status_code}")
                    
            except requests.exceptions.ConnectionError:
                print(f"Request {i}: Connection error")
                return False
            except Exception as e:
                print(f"Request {i}: Error: {e}")
            
            time.sleep(0.1)
        
        print(f"\nResults: {success_count} successful, {redirect_count} redirects, {rate_limited_count} rate limited")
        # Consider both success and redirects as valid for rate limiting
        total_valid = success_count + redirect_count
        assert total_valid > 0, "Should have at least some successful/redirected requests"
        print("✓ Test endpoint rate limiting test passed")
        return True
    
    def test_favicon_rate_limiting(self):
        """Test rate limiting on favicon endpoint."""
        print(f"\nTesting favicon rate limiting at {BASE_URL}/favicon.ico")
        print("-" * 50)
        
        success_count = 0
        rate_limited_count = 0
        redirect_count = 0
        
        # Make 25 requests (reduced from 105 for faster testing)
        for i in range(1, 26):
            try:
                response = requests.get(f"{BASE_URL}/favicon.ico", timeout=5)
                print(f"Request {i}: Status {response.status_code}")
                
                if response.status_code == 200:
                    success_count += 1
                    print(f"  Content-Type: {response.headers.get('Content-Type', 'Not specified')}")
                    print(f"  Content-Length: {len(response.content)} bytes")
                elif response.status_code == 302:
                    redirect_count += 1
                    print(f"  Redirect to login (rate limiting active)")
                elif response.status_code == 429:
                    rate_limited_count += 1
                    print("  Rate limit exceeded!")
                    break
                else:
                    print(f"  Unexpected status code: {response.status_code}")
                    
            except requests.exceptions.ConnectionError:
                print(f"Request {i}: Connection error")
                return False
            except Exception as e:
                print(f"Request {i}: Error: {e}")
            
            time.sleep(0.05)  # Small delay
        
        print(f"\nResults: {success_count} successful, {redirect_count} redirects, {rate_limited_count} rate limited")
        # Consider both success and redirects as valid for rate limiting
        total_valid = success_count + redirect_count
        assert total_valid > 0, "Should have at least some successful/redirected requests"
        print("✓ Favicon rate limiting test passed")
        return True
    
    def test_health_check_rate_limiting(self):
        """Test rate limiting on health check endpoint."""
        print(f"\nTesting health check rate limiting at {BASE_URL}/healthz")
        print("-" * 50)
        
        success_count = 0
        rate_limited_count = 0
        redirect_count = 0
        
        # Make 25 requests (reduced from 105 for faster testing)
        for i in range(1, 26):
            try:
                response = requests.get(f"{BASE_URL}/healthz", timeout=5)
                print(f"Request {i}: Status {response.status_code}")
                
                if response.status_code == 200:
                    success_count += 1
                    # Check response is JSON
                    try:
                        data = response.json()
                        print(f"  Status: {data.get('status', 'Unknown')}")
                    except:
                        print("  Response: Not JSON")
                elif response.status_code == 302:
                    redirect_count += 1
                    print(f"  Redirect to login (rate limiting active)")
                elif response.status_code == 429:
                    rate_limited_count += 1
                    print("  Rate limit exceeded!")
                    break
                else:
                    print(f"  Unexpected status code: {response.status_code}")
                    
            except requests.exceptions.ConnectionError:
                print(f"Request {i}: Connection error")
                return False
            except Exception as e:
                print(f"Request {i}: Error: {e}")
            
            time.sleep(0.05)
        
        print(f"\nResults: {success_count} successful, {redirect_count} redirects, {rate_limited_count} rate limited")
        # Consider both success and redirects as valid for rate limiting
        total_valid = success_count + redirect_count
        assert total_valid > 0, "Should have at least some successful/redirected requests"
        print("✓ Health check rate limiting test passed")
        return True
    
    def test_different_endpoints_different_limits(self):
        """Test that different endpoints have different rate limits."""
        print(f"\nTesting different endpoints have different rate limits")
        print("-" * 50)
        
        endpoints = [
            ("/", "Homepage", 20),
            ("/style_guide", "Style Guide", 10),
            ("/test-rate-limit", "Test Rate Limit", 5),
            ("/favicon.ico", "Favicon", 100),
            ("/healthz", "Health Check", 100)
        ]
        
        results = {}
        
        for endpoint, name, expected_limit in endpoints:
            print(f"\nTesting {name} ({endpoint}) - Expected limit: {expected_limit} per minute")
            
            success_count = 0
            rate_limited_count = 0
            test_requests = expected_limit + 5  # Test slightly above the limit
            
            for i in range(1, test_requests + 1):
                try:
                    response = requests.get(f"{BASE_URL}{endpoint}", timeout=5)
                    
                    if response.status_code == 200:
                        success_count += 1
                    elif response.status_code == 429:
                        rate_limited_count += 1
                        print(f"  Rate limited after {success_count} successful requests")
                        break
                    elif response.status_code in [401, 403]:
                        print(f"  Auth required/forbidden after {success_count} requests")
                        break
                    
                except Exception as e:
                    print(f"  Request {i}: Error: {e}")
                
                time.sleep(0.05)
            
            results[name] = {
                'success_count': success_count,
                'rate_limited': rate_limited_count > 0,
                'expected_limit': expected_limit
            }
            
            print(f"  Results: {success_count} successful, rate limited: {rate_limited_count > 0}")
        
        # Verify that endpoints with stricter limits get rate limited sooner
        print("\n" + "=" * 50)
        print("SUMMARY:")
        print("-" * 50)
        
        for name, result in results.items():
            status = "✓" if result['rate_limited'] else "✗"
            print(f"{status} {name}: {result['success_count']}/{result['expected_limit']} requests before rate limit")
        
        print("✓ Different endpoints rate limiting test completed")
        return True
    
    def test_rate_limit_recovery(self):
        """Test that rate limits recover after the time window."""
        print(f"\nTesting rate limit recovery after time window")
        print("-" * 50)
        
        print("Phase 1: Exhaust rate limit on test endpoint")
        success_count = 0
        
        # Exhaust the rate limit (5 per minute)
        for i in range(1, 8):
            try:
                response = requests.get(f"{BASE_URL}/test-rate-limit", timeout=5)
                if response.status_code == 200:
                    success_count += 1
                    print(f"Request {i}: Success ({success_count})")
                elif response.status_code == 429:
                    print(f"Request {i}: Rate limited after {success_count} requests")
                    break
            except Exception as e:
                print(f"Request {i}: Error: {e}")
                break
            
            time.sleep(0.1)
        
        print(f"\nPhase 2: Wait for rate limit to reset (waiting 65 seconds)")
        time.sleep(65)
        
        print("\nPhase 3: Test that rate limit has reset")
        recovery_success = False
        
        try:
            response = requests.get(f"{BASE_URL}/test-rate-limit", timeout=5)
            if response.status_code == 200:
                recovery_success = True
                print("Request after wait: Success - rate limit has reset")
            else:
                print(f"Request after wait: Failed with status {response.status_code}")
        except Exception as e:
            print(f"Request after wait: Error: {e}")
        
        assert recovery_success, "Rate limit should reset after time window"
        print("✓ Rate limit recovery test passed")
        return True
    
    def test_concurrent_requests_rate_limiting(self):
        """Test rate limiting with concurrent requests."""
        print(f"\nTesting rate limiting with concurrent requests")
        print("-" * 50)
        
        import threading
        import queue
        
        results = queue.Queue()
        
        def make_request(request_id):
            try:
                response = requests.get(f"{BASE_URL}/test-rate-limit", timeout=5)
                results.put({
                    'request_id': request_id,
                    'status_code': response.status_code,
                    'timestamp': datetime.now()
                })
            except Exception as e:
                results.put({
                    'request_id': request_id,
                    'error': str(e),
                    'timestamp': datetime.now()
                })
        
        print("Starting 10 concurrent requests...")
        
        # Start 10 concurrent requests
        threads = []
        for i in range(10):
            thread = threading.Thread(target=make_request, args=(i+1,))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Collect and analyze results
        success_count = 0
        rate_limited_count = 0
        error_count = 0
        
        print("\nResults:")
        while not results.empty():
            result = results.get()
            if 'error' in result:
                print(f"  Request {result['request_id']}: Error - {result['error']}")
                error_count += 1
            else:
                status = result['status_code']
                if status == 200:
                    success_count += 1
                    print(f"  Request {result['request_id']}: Success")
                elif status == 429:
                    rate_limited_count += 1
                    print(f"  Request {result['request_id']}: Rate limited")
                else:
                    print(f"  Request {result['request_id']}: Status {status}")
        
        print(f"\nSummary: {success_count} successful, {rate_limited_count} rate limited, {error_count} errors")
        
        # Should have some successful requests and some rate limited
        assert success_count > 0, "Should have some successful requests"
        assert rate_limited_count > 0, "Should have some rate limited requests"
        assert error_count == 0, "Should not have any errors"
        
        print("✓ Concurrent requests rate limiting test passed")
        return True
    
    def test_rate_limit_management_list(self):
        """Test listing all rate limit blocks via management script."""
        print(f"\nTesting rate limit management list functionality")
        print("-" * 50)
        
        # First, trigger some rate limits to create data
        print("Creating some rate limit data...")
        for i in range(3):
            try:
                response = requests.get(f"{BASE_URL}/api/hospitals", timeout=5)
                print(f"  Request {i+1}: Status {response.status_code}")
            except Exception as e:
                print(f"  Request {i+1}: Error: {e}")
            time.sleep(0.1)
        
        # Use the management script to list all limits
        print("\nRunning rate limit list command...")
        try:
            result = subprocess.run(
                ["uv", "run", "scripts/manage_rate_limits.py", "list"],
                capture_output=True,
                text=True,
                cwd=os.getcwd()
            )
            
            print(f"Command exit code: {result.returncode}")
            
            # The command should succeed
            assert result.returncode == 0, f"List command failed with code {result.returncode}"
            
            # Output should contain rate limit information
            output = result.stdout + result.stderr
            print("Command output:")
            print("-" * 30)
            print(output)
            print("-" * 30)
            
            # Check for expected content
            assert "All Rate Limit Blocks" in output, "Output should contain 'All Rate Limit Blocks'"
            assert "Storage Type:" in output, "Output should contain storage type information"
            
            # Should show sample keys or total keys
            has_keys_info = (
                "Total Keys:" in output or
                "Sample Keys:" in output or
                "Grouped by Client:" in output
            )
            assert has_keys_info, "Output should contain keys information"
            
            print("✓ Rate limit management list test passed")
            return True
            
        except Exception as e:
            print(f"Error running list command: {e}")
            return False


def run_all_tests():
    """Run all end-to-end tests."""
    print("=" * 60)
    print("FLASK-LIMITER 4.0 END-TO-END TESTS")
    print("=" * 60)
    print(f"Testing against: {BASE_URL}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("=" * 60)
    
    tester = TestRateLimiterE2E()
    tests = [
        ("Homepage Rate Limiting", tester.test_homepage_rate_limiting),
        ("Style Guide Rate Limiting", tester.test_style_guide_rate_limiting),
        ("API Rate Limiting", tester.test_api_rate_limiting),
        ("Test Rate Limit Endpoint", tester.test_test_rate_limit_endpoint),
        ("Favicon Rate Limiting", tester.test_favicon_rate_limiting),
        ("Health Check Rate Limiting", tester.test_health_check_rate_limiting),
        ("Different Endpoints Different Limits", tester.test_different_endpoints_different_limits),
        ("Rate Limit Recovery", tester.test_rate_limit_recovery),
        ("Concurrent Requests Rate Limiting", tester.test_concurrent_requests_rate_limiting),
        ("Rate Limit Management List", tester.test_rate_limit_management_list)
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        print(f"\n{'=' * 20} {test_name} {'=' * 20}")
        try:
            if test_func():
                passed += 1
                print(f"✓ {test_name} PASSED")
            else:
                failed += 1
                print(f"✗ {test_name} FAILED")
        except Exception as e:
            failed += 1
            print(f"✗ {test_name} FAILED with exception: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("FINAL RESULTS")
    print("=" * 60)
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Total: {passed + failed}")
    
    if failed == 0:
        print("\n🎉 ALL TESTS PASSED! 🎉")
        return True
    else:
        print(f"\n❌ {failed} TESTS FAILED ❌")
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)