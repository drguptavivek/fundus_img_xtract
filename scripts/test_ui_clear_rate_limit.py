#!/usr/bin/env python3
"""
Test script to verify UI rate limit clearing for IP addresses.
"""

import os
import sys
import redis
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

def test_ip_rate_limit_clear():
    """Test clearing rate limits for IP addresses as done from the UI."""
    
    # Get Redis configuration from environment
    redis_url = os.getenv('REDIS_URL') or os.getenv('RATELIMIT_REDIS_URL', 'redis://localhost:6379/10')
    
    print(f"Connecting to Redis: {redis_url}")
    
    try:
        # Create Redis client
        r = redis.from_url(redis_url)
        
        # Add a test rate limit for IP 127.0.0.1
        test_key = "LIMITS:LIMITER/ip:127.0.0.1/auth.login:GET/20/1/minute"
        r.set(test_key, "10", ex=300)  # Expire in 5 minutes
        print(f"Added test key: {test_key}")
        
        # Check current rate limit keys for ip:127.0.0.1
        print("\n=== Before clearing ===")
        ip_keys = r.keys("LIMITS:LIMITER/ip:127.0.0.1/*")
        print(f"Found {len(ip_keys)} rate limit keys for ip:127.0.0.1")
        for key in ip_keys:
            key_str = key.decode('utf-8') if isinstance(key, bytes) else key
            value = r.get(key)
            value_str = value.decode('utf-8') if isinstance(value, bytes) else str(value) if value else "None"
            print(f"  - {key_str}: {value_str}")
        
        # Test clearing with the rate limiter function using the format from UI
        print("\n=== Clearing rate limits for ip:127.0.0.1 ===")
        from app import create_app
        app = create_app()
        
        with app.app_context():
            from utils.rate_limiter import clear_rate_limit, get_rate_limit_status
            
            # Clear the rate limit using just the IP (as the UI would do)
            # The UI now passes the full client_key (ip:127.0.0.1)
            result = clear_rate_limit(key="ip:127.0.0.1")
            print(f"Clear rate limit result: {result}")
            
            # Check after clearing
            ip_keys = r.keys("LIMITS:LIMITER/ip:127.0.0.1/*")
            print(f"\n=== After clearing ===")
            print(f"Found {len(ip_keys)} rate limit keys for ip:127.0.0.1")
            for key in ip_keys:
                key_str = key.decode('utf-8') if isinstance(key, bytes) else key
                value = r.get(key)
                value_str = value.decode('utf-8') if isinstance(value, bytes) else str(value) if value else "None"
                print(f"  - {key_str}: {value_str}")
        
        # Test the parse_rate_limit_key function
        print("\n=== Testing parse_rate_limit_key function ===")
        from admin.rate_limit_admin import parse_rate_limit_key
        
        test_keys = [
            "LIMITS:LIMITER/ip:127.0.0.1/global/100/1/minute",
            "LIMITS:LIMITER/ip:127.0.0.1/auth.login:GET/20/1/minute",
            "LIMITS:LIMITER/user:1/global/1000/1/hour"
        ]
        
        for test_key in test_keys:
            parsed = parse_rate_limit_key(test_key)
            print(f"\nKey: {test_key}")
            print(f"  Client Type: {parsed.get('client_type')}")
            print(f"  Client Value: {parsed.get('client_value')}")
            print(f"  Client Key: {parsed.get('client_key')}")
            print(f"  Endpoint: {parsed.get('endpoint')}")
            print(f"  Limit: {parsed.get('limit')}")
        
        return True
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_ip_rate_limit_clear()