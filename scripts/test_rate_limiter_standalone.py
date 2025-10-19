#!/usr/bin/env python3
"""
Standalone script to test rate limiting and flask-limiter logger.
This script can be run against a running application to verify rate limiting works.
"""

import os
import sys
import time
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import threading

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

import requests


def get_base_url():
    """Get base URL from environment or use default."""
    base_url = os.getenv("BASE_URL", "http://127.0.0.1:5000")
    port = os.getenv("FLASK_PORT", "5000")
    
    # If BASE_URL doesn't include port, add it
    if f":{port}" not in base_url:
        if base_url.endswith("/"):
            base_url = base_url[:-1]
        base_url = f"{base_url}:{port}"
    
    return base_url


def check_server(base_url):
    """Check if the server is running."""
    try:
        response = requests.get(f"{base_url}/", timeout=5)
        return response.status_code == 200
    except Exception as e:
        print(f"❌ Server not accessible at {base_url}: {e}")
        return False


def make_request(base_url, endpoint, request_id):
    """Make a single request to the test endpoint."""
    try:
        response = requests.get(f"{base_url}{endpoint}", timeout=5)
        return {
            "request_id": request_id,
            "status_code": response.status_code,
            "response": response.text[:100] if response.text else "",
            "headers": dict(response.headers)
        }
    except Exception as e:
        return {
            "request_id": request_id,
            "status_code": 0,
            "error": str(e)
        }


def test_rate_limiting(base_url):
    """Test rate limiting by making multiple requests."""
    print(f"\n🧪 Testing rate limiting at {base_url}/test-rate-limit")
    print("=" * 60)
    
    # Test 1: Sequential requests
    print("\n1️⃣  Testing sequential requests...")
    sequential_results = []
    for i in range(8):
        result = make_request(base_url, "/test-rate-limit", i)
        sequential_results.append(result)
        status = "✅ SUCCESS" if result["status_code"] == 200 else \
                "⚠️  RATE LIMITED" if result["status_code"] == 429 else "❌ ERROR"
        print(f"   Request {i}: {status} (Status: {result['status_code']})")
        time.sleep(0.2)  # Small delay between requests
    
    # Check if any were rate limited
    rate_limited = sum(1 for r in sequential_results if r["status_code"] == 429)
    if rate_limited > 0:
        print(f"   ✅ {rate_limited} requests were rate limited")
    else:
        print("   ⚠️  No requests were rate limited (try increasing request rate)")
    
    # Test 2: Concurrent requests
    print("\n2️⃣  Testing concurrent requests...")
    concurrent_results = []
    
    def worker(request_id):
        result = make_request(base_url, "/test-rate-limit", request_id)
        concurrent_results.append(result)
    
    # Start multiple threads
    threads = []
    for i in range(10):
        thread = threading.Thread(target=worker, args=(i,))
        threads.append(thread)
        thread.start()
    
    # Wait for all threads to complete
    for thread in threads:
        thread.join()
    
    # Analyze concurrent results
    concurrent_success = sum(1 for r in concurrent_results if r["status_code"] == 200)
    concurrent_limited = sum(1 for r in concurrent_results if r["status_code"] == 429)
    concurrent_errors = sum(1 for r in concurrent_results if r["status_code"] not in [200, 429])
    
    print(f"   ✅ Successful: {concurrent_success}")
    print(f"   ⚠️  Rate limited: {concurrent_limited}")
    print(f"   ❌ Errors: {concurrent_errors}")
    
    return rate_limited > 0 or concurrent_limited > 0


def check_log_files():
    """Check log files for rate limit entries."""
    print("\n📋 Checking log files...")
    print("-" * 40)
    
    log_dir = Path(project_root) / "logs"
    flask_limiter_log = log_dir / "flask_limiter.log"
    rate_limit_log = log_dir / "rate_limit.log"
    
    # Check flask-limiter log
    if flask_limiter_log.exists():
        with open(flask_limiter_log, 'r') as f:
            lines = f.readlines()
            recent_lines = [line for line in lines[-10:] if "Rate limit violation" in line]
            if recent_lines:
                print(f"✅ flask_limiter.log: Found {len(recent_lines)} recent rate limit violations")
                for line in recent_lines[-3:]:  # Show last 3
                    print(f"   {line.strip()}")
            else:
                print("⚠️  flask_limiter.log: No recent rate limit violations found")
    else:
        print("❌ flask_limiter.log: File not found")
    
    # Check rate_limit log
    if rate_limit_log.exists():
        with open(rate_limit_log, 'r') as f:
            lines = f.readlines()
            recent_lines = [line for line in lines[-10:] if "Rate limit violation" in line]
            if recent_lines:
                print(f"✅ rate_limit.log: Found {len(recent_lines)} recent rate limit violations")
                for line in recent_lines[-3:]:  # Show last 3
                    print(f"   {line.strip()}")
            else:
                print("⚠️  rate_limit.log: No recent rate limit violations found")
    else:
        print("❌ rate_limit.log: File not found")


def main():
    """Main test function."""
    print("🚀 Rate Limiter Test Script")
    print("=" * 60)
    
    # Get configuration
    base_url = get_base_url()
    print(f"📍 Target URL: {base_url}")
    
    # Check if server is running
    if not check_server(base_url):
        print("\n❌ Please start the server first:")
        print("   uv run app.py")
        print("   or")
        print("   python app.py")
        sys.exit(1)
    
    print("✅ Server is running")
    
    # Test rate limiting
    rate_limiting_works = test_rate_limiting(base_url)
    
    # Check log files
    check_log_files()
    
    # Summary
    print("\n📊 Test Summary")
    print("=" * 60)
    if rate_limiting_works:
        print("✅ Rate limiting is working correctly")
        print("✅ Check log files for proper flask-limiter logger output")
    else:
        print("⚠️  Rate limiting may not be working as expected")
        print("   - Try increasing the request rate")
        print("   - Check that RATELIMIT_ENABLED=true in your .env")
    
    print("\n🔍 To view logs in real-time:")
    print(f"   tail -f {project_root}/logs/flask_limiter.log")
    print(f"   tail -f {project_root}/logs/rate_limit.log")


if __name__ == "__main__":
    main()