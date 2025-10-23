#!/usr/bin/env python3
"""
Test script to verify rate limit clearing functionality.
"""

import os
import sys
import redis
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

def test_clear_rate_limit():
    """Test clearing rate limits for a specific key."""
    
    # Get Redis configuration from environment
    redis_url = os.getenv('REDIS_URL') or os.getenv('RATELIMIT_REDIS_URL', 'redis://localhost:6379/10')
    
    print(f"Connecting to Redis: {redis_url}")
    
    try:
        # Create Redis client
        r = redis.from_url(redis_url)
        
        # Check current rate limit keys for user:1
        print("\n=== Before clearing ===")
        user_keys = r.keys("LIMITS:LIMITER/user:1/*")
        print(f"Found {len(user_keys)} rate limit keys for user:1")
        for key in user_keys:
            key_str = key.decode('utf-8') if isinstance(key, bytes) else key
            value = r.get(key)
            value_str = value.decode('utf-8') if isinstance(value, bytes) else str(value) if value else "None"
            print(f"  - {key_str}: {value_str}")
        
        # Clear rate limits for user:1
        print("\n=== Clearing rate limits for user:1 ===")
        pattern = "LIMITS:LIMITER/user:1/*"
        keys_to_delete = r.keys(pattern)
        if keys_to_delete:
            r.delete(*keys_to_delete)
            print(f"Deleted {len(keys_to_delete)} keys")
        else:
            print("No keys to delete")
        
        # Check after clearing
        print("\n=== After clearing ===")
        user_keys = r.keys("LIMITS:LIMITER/user:1/*")
        print(f"Found {len(user_keys)} rate limit keys for user:1")
        for key in user_keys:
            key_str = key.decode('utf-8') if isinstance(key, bytes) else key
            value = r.get(key)
            value_str = value.decode('utf-8') if isinstance(value, bytes) else str(value) if value else "None"
            print(f"  - {key_str}: {value_str}")
        
        # Test with the rate limiter function
        print("\n=== Testing with rate limiter function ===")
        from app import create_app
        app = create_app()
        
        with app.app_context():
            from utils.rate_limiter import clear_rate_limit, get_rate_limit_status
            
            # Add some test rate limits first
            test_key = "LIMITS:LIMITER/user:1/test_endpoint/10/1/minute"
            r.set(test_key, "5")
            print(f"Added test key: {test_key}")
            
            # Check status before clearing
            status = get_rate_limit_status("user:1")
            print(f"Status before clearing: {status.get('total_matching_keys', 0)} matching keys")
            
            # Clear the rate limit
            result = clear_rate_limit(key="user:1")
            print(f"Clear rate limit result: {result}")
            
            # Check status after clearing
            status = get_rate_limit_status("user:1")
            print(f"Status after clearing: {status.get('total_matching_keys', 0)} matching keys")
        
        return True
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_clear_rate_limit()