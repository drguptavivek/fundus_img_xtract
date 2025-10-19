#!/usr/bin/env python3
"""
Script to manage rate limits from the command line.
This can be used to clear rate limits or check their status.
"""

import os
import sys
import argparse
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables
from dotenv import load_dotenv
load_dotenv()


def init_app():
    """Initialize the Flask app to access rate limiter."""
    from app import create_app
    app = create_app()
    with app.app_context():
        return app


def clear_rate_limit(key=None, limit=None):
    """Clear a rate limit block."""
    from utils.rate_limiter import clear_rate_limit as clear_limit_func
    
    print(f"Clearing rate limit...")
    if key:
        print(f"  Key: {key}")
    if limit:
        print(f"  Limit: {limit}")
    
    success = clear_limit_func(key=key, limit=limit)
    
    if success:
        print("✅ Rate limit cleared successfully")
        return True
    else:
        print("❌ Failed to clear rate limit")
        return False


def get_status(key=None):
    """Get rate limit status."""
    from utils.rate_limiter import get_rate_limit_status
    
    print("Rate Limit Status")
    print("=" * 60)
    
    status = get_rate_limit_status(key=key)
    
    if "error" in status:
        print(f"❌ Error: {status['error']}")
        return False
    
    if key:
        print(f"Key: {status.get('key', 'N/A')}")
        
        if "matching_keys" in status:
            print(f"\nMatching Limits ({len(status['matching_keys'])}):")
            for k in status['matching_keys']:
                print(f"  - {k}")
        
        if "limits" in status:
            print(f"\nLimit Details:")
            for k, v in status['limits'].items():
                print(f"  {k}: {v}")
    else:
        print(f"Storage Type: {status.get('storage_type', 'Unknown')}")
        
        if "total_keys" in status:
            print(f"Total Keys: {status['total_keys']}")
        
        if "keys" in status:
            print(f"\nSample Keys (showing first {len(status['keys'])}):")
            for k in status['keys']:
                print(f"  - {k}")
    
    return True


def get_current_key():
    """Get the current rate limit key for a request."""
    from utils.rate_limiter import get_rate_limit_key
    
    try:
        # Create a mock request context
        from flask import Flask
        app = Flask(__name__)
        
        with app.test_request_context('/'):
            key = get_rate_limit_key()
            print(f"Current rate limit key: {key}")
            return key
    except Exception as e:
        print(f"Error getting current key: {e}")
        return None


def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Manage rate limits")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Clear command
    clear_parser = subparsers.add_parser("clear", help="Clear rate limits")
    clear_parser.add_argument("--key", help="Key to clear (e.g., ip:127.0.0.1 or user:123)")
    clear_parser.add_argument("--limit", help="Specific limit to clear (e.g., '5 per minute')")
    
    # Status command
    status_parser = subparsers.add_parser("status", help="Show rate limit status")
    status_parser.add_argument("--key", help="Key to check (e.g., ip:127.0.0.1 or user:123)")
    
    # Current key command
    subparsers.add_parser("my-key", help="Get current rate limit key")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Initialize app
    print("Initializing application...")
    app = init_app()
    
    # Execute command
    if args.command == "clear":
        if not args.key:
            print("❌ --key is required for clear command")
            sys.exit(1)
        clear_rate_limit(key=args.key, limit=args.limit)
    
    elif args.command == "status":
        get_status(key=args.key)
    
    elif args.command == "my-key":
        get_current_key()


if __name__ == "__main__":
    main()