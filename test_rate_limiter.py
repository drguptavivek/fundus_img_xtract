#!/usr/bin/env python3
"""
Test script to verify flask-limiter logger is working correctly.
This script will make rapid requests to a test endpoint to trigger rate limiting.
"""

import requests
import time
import sys
from concurrent.futures import ThreadPoolExecutor
import threading

# Configuration
BASE_URL = "http://127.0.0.1:5000"
TEST_ENDPOINT = "/test-rate-limit"
THREAD_COUNT = 5
REQUESTS_PER_THREAD = 10
DELAY_BETWEEN_REQUESTS = 0.1  # seconds

def make_request(thread_id, request_id):
    """Make a single request to the test endpoint."""
    try:
        response = requests.get(f"{BASE_URL}{TEST_ENDPOINT}", timeout=5)
        return {
            "thread_id": thread_id,
            "request_id": request_id,
            "status_code": response.status_code,
            "response": response.text[:100]  # First 100 chars
        }
    except Exception as e:
        return {
            "thread_id": thread_id,
            "request_id": request_id,
            "status_code": 0,
            "error": str(e)
        }

def test_rate_limiter():
    """Test the rate limiter by making multiple concurrent requests."""
    print(f"Testing rate limiter with {THREAD_COUNT} threads, {REQUESTS_PER_THREAD} requests per thread")
    print(f"Target endpoint: {BASE_URL}{TEST_ENDPOINT}")
    print("=" * 60)
    
    results = []
    
    def thread_worker(thread_id):
        """Worker function for each thread."""
        for i in range(REQUESTS_PER_THREAD):
            result = make_request(thread_id, i)
            results.append(result)
            time.sleep(DELAY_BETWEEN_REQUESTS)
    
    # Create and start threads
    threads = []
    start_time = time.time()
    
    for i in range(THREAD_COUNT):
        thread = threading.Thread(target=thread_worker, args=(i,))
        threads.append(thread)
        thread.start()
    
    # Wait for all threads to complete
    for thread in threads:
        thread.join()
    
    end_time = time.time()
    
    # Analyze results
    total_requests = len(results)
    success_requests = sum(1 for r in results if 200 <= r["status_code"] < 300)
    rate_limited_requests = sum(1 for r in results if r["status_code"] == 429)
    other_errors = total_requests - success_requests - rate_limited_requests
    
    print(f"\nTest completed in {end_time - start_time:.2f} seconds")
    print(f"Total requests: {total_requests}")
    print(f"Successful requests (2xx): {success_requests}")
    print(f"Rate limited requests (429): {rate_limited_requests}")
    print(f"Other errors: {other_errors}")
    
    # Show some sample results
    print("\nSample results:")
    for result in results[:5]:
        if result["status_code"] == 429:
            print(f"  Thread {result['thread_id']}, Request {result['request_id']}: RATE LIMITED")
        elif 200 <= result["status_code"] < 300:
            print(f"  Thread {result['thread_id']}, Request {result['request_id']}: SUCCESS")
        else:
            print(f"  Thread {result['thread_id']}, Request {result['request_id']}: ERROR {result['status_code']}")
    
    print("\nCheck the following log files to verify rate limiter logging:")
    print("1. logs/flask_limiter.log - Should contain rate limit violations")
    print("2. logs/rate_limit.log - Should also contain rate limit violations")
    
    if rate_limited_requests > 0:
        print("\n✅ Rate limiting is working! Check the log files for proper logging.")
    else:
        print("\n⚠️  No rate limits were triggered. Consider increasing the request rate or decreasing limits.")

if __name__ == "__main__":
    # Check if the server is running
    try:
        response = requests.get(f"{BASE_URL}/", timeout=2)
        print(f"Server is running at {BASE_URL}")
    except Exception as e:
        print(f"❌ Server is not running at {BASE_URL}: {e}")
        print("Please start the server with: uv run app.py")
        sys.exit(1)
    
    # Check if the test endpoint exists
    try:
        response = requests.get(f"{BASE_URL}{TEST_ENDPOINT}", timeout=2)
        if response.status_code == 404:
            print(f"❌ Test endpoint {TEST_ENDPOINT} not found.")
            print("Please add the test endpoint to app.py (see instructions in the script)")
            sys.exit(1)
    except Exception as e:
        print(f"Error checking test endpoint: {e}")
    
    test_rate_limiter()