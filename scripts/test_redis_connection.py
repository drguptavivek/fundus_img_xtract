#!/usr/bin/env python3
"""
Test script to verify Redis connection for rate limiting.
"""

import os
import sys
import redis
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

def test_redis_connection():
    """Test Redis connection using the same configuration as the rate limiter."""
    
    # Get Redis configuration from environment
    redis_url = os.getenv('REDIS_URL') or os.getenv('RATELIMIT_REDIS_URL', 'redis://localhost:6379/10')
    
    print(f"Testing Redis connection to: {redis_url}")
    
    try:
        # Create Redis client
        r = redis.from_url(redis_url)
        
        # Test connection
        result = r.ping()
        print(f"✓ Redis ping successful: {result}")
        
        # Get Redis info
        info = r.info()
        print(f"✓ Redis version: {info.get('redis_version')}")
        print(f"✓ Connected clients: {info.get('connected_clients')}")
        print(f"✓ Used memory: {info.get('used_memory_human')}")
        
        # Test database size
        db_size = r.dbsize()
        print(f"✓ Database size (keys): {db_size}")
        
        # Test setting and getting a value
        test_key = "test:rate:limit:connection"
        r.set(test_key, "test_value", ex=10)  # Expire in 10 seconds
        value = r.get(test_key)
        print(f"✓ Test set/get successful: {value}")
        
        # Clean up test key
        r.delete(test_key)
        
        # Check for rate limit keys
        keys = r.keys("LIMITS:*")
        print(f"✓ Found {len(keys)} rate limit keys")
        
        if keys:
            print("Sample rate limit keys:")
            for key in keys[:5]:  # Show first 5 keys
                key_str = key.decode('utf-8') if isinstance(key, bytes) else key
                print(f"  - {key_str}")
        
        return True
        
    except redis.ConnectionError as e:
        print(f"✗ Redis connection error: {e}")
        print("\nPossible solutions:")
        print("1. Make sure Redis server is running: redis-server")
        print("2. Check if Redis is accessible on the configured port")
        print("3. Verify the Redis URL in .env file")
        return False
        
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        return False

def test_rate_limiter_storage():
    """Test the rate limiter's Redis storage directly."""
    
    print("\nTesting rate limiter Redis storage...")
    
    try:
        # Create Flask app to initialize the rate limiter
        from app import create_app
        app = create_app()
        
        with app.app_context():
            # Import the rate limiter
            from utils.rate_limiter import limiter
            
            if not limiter:
                print("✗ Rate limiter not initialized")
                return False
        
        if not limiter._storage:
            print("✗ Rate limiter storage not initialized")
            return False
        
        storage_type = type(limiter._storage).__name__
        print(f"✓ Rate limiter storage type: {storage_type}")
        
        # Check if it's Redis storage
        if hasattr(limiter._storage, 'storage'):
            redis_client = limiter._storage.storage
            print("✓ Redis client found in rate limiter storage")
            
            # Test Redis operations through the limiter
            test_key = "test:limiter:connection"
            redis_client.set(test_key, "test_value", ex=10)
            value = redis_client.get(test_key)
            print(f"✓ Limiter Redis test successful: {value}")
            redis_client.delete(test_key)
            
        elif hasattr(limiter._storage, '_storage'):
            print("✓ Memory storage detected (not Redis)")
            
        else:
            print("✗ Unknown storage type")
            return False
        
        return True
        
    except Exception as e:
        print(f"✗ Error testing rate limiter storage: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("=== Redis Connection Test ===\n")
    
    redis_ok = test_redis_connection()
    limiter_ok = test_rate_limiter_storage()
    
    print("\n=== Summary ===")
    if redis_ok and limiter_ok:
        print("✓ All tests passed! Redis is properly configured for rate limiting.")
        sys.exit(0)
    else:
        print("✗ Some tests failed. Check the errors above.")
        sys.exit(1)