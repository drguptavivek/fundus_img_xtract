#!/usr/bin/env python3
"""
Check the actual Redis keys for rate limiting.
"""

import os
import sys
import redis
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

def check_redis_keys():
    """Check the actual Redis keys for rate limiting."""
    
    # Get Redis configuration from environment
    redis_url = os.getenv('REDIS_URL') or os.getenv('RATELIMIT_REDIS_URL', 'redis://localhost:6379/10')
    
    print(f"Connecting to Redis: {redis_url}")
    
    try:
        # Create Redis client
        r = redis.from_url(redis_url)
        
        # Get all rate limit keys
        keys = r.keys("LIMITS:*")
        print(f"\nFound {len(keys)} rate limit keys:")
        
        for key in keys:
            key_str = key.decode('utf-8') if isinstance(key, bytes) else key
            print(f"  - {key_str}")
            
            # Get the value and TTL
            value = r.get(key)
            ttl = r.ttl(key)
            value_str = value.decode('utf-8') if isinstance(value, bytes) else str(value) if value else "None"
            print(f"    Value: {value_str}, TTL: {ttl}")
        
        # Check for a specific user pattern
        print("\n\nChecking for user:1 pattern:")
        user_keys = r.keys("*user:1*")
        for key in user_keys:
            key_str = key.decode('utf-8') if isinstance(key, bytes) else key
            print(f"  - {key_str}")
        
        return True
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    check_redis_keys()