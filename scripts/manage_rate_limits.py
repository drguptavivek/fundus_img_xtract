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


def list_all_blocks():
    """List all rate limit blocks currently in place."""
    from utils.rate_limiter import get_rate_limit_status
    
    print("All Rate Limit Blocks")
    print("=" * 60)
    
    # Get overall status
    status = get_rate_limit_status()
    
    if "error" in status:
        print(f"❌ Error: {status['error']}")
        return False
    
    print(f"Storage Type: {status.get('storage_type', 'Unknown')}")
    print(f"Total Keys: {status.get('total_keys', 0)}")
    
    # Show Redis info if available
    if "redis_info" in status:
        redis_info = status["redis_info"]
        print(f"\nRedis Information:")
        print(f"  Used Memory: {redis_info.get('used_memory', 'N/A')}")
        print(f"  Connected Clients: {redis_info.get('connected_clients', 'N/A')}")
        print(f"  Total Commands: {redis_info.get('total_commands_processed', 'N/A')}")
    
    # Show sample keys
    if "sample_keys" in status and status["sample_keys"]:
        print(f"\nSample Keys (showing first {len(status['sample_keys'])}):")
        for key in status["sample_keys"]:
            print(f"  - {key}")
    
    # Group keys by IP or User
    if "sample_keys" in status and status["sample_keys"]:
        print(f"\nGrouped by Client:")
        ip_keys = []
        user_keys = []
        other_keys = []
        
        for key in status["sample_keys"]:
            if key.startswith("ip:"):
                ip_keys.append(key)
            elif key.startswith("user:"):
                user_keys.append(key)
            else:
                other_keys.append(key)
        
        if ip_keys:
            print(f"\n  IP-based Limits ({len(ip_keys)}):")
            for key in ip_keys[:5]:  # Show first 15
                print(f"    - {key}")
            if len(ip_keys) > 15:
                print(f"    ... and {len(ip_keys) - 15} more")
        
        if user_keys:
            print(f"\n  User-based Limits ({len(user_keys)}):")
            for key in user_keys[:15]:  # Show first 15
                print(f"    - {key}")
            if len(user_keys) > 15:
                print(f"    ... and {len(user_keys) - 15} more")
        
        if other_keys:
            print(f"\n  Other Limits ({len(other_keys)}):")
            for key in other_keys[:5]:  # Show first 15
                print(f"    - {key}")
            if len(other_keys) > 15:
                print(f"    ... and {len(other_keys) - 15} more")
    
    return True


def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Manage rate limits")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Clear command
    clear_parser = subparsers.add_parser("clear", help="Clear rate limits")
    clear_parser.add_argument("--key", help="Key to clear (e.g., ip:127.0.0.1 or user:123)")
    clear_parser.add_argument("--limit", help="Specific limit to clear (e.g., '15 per minute')")
    
    # Clear all command
    subparsers.add_parser("clear-all", help="Clear ALL rate limits (use with caution)")
    
    # Status command
    status_parser = subparsers.add_parser("status", help="Show rate limit status")
    status_parser.add_argument("--key", help="Key to check (e.g., ip:127.0.0.1 or user:123)")
    
    # List command
    list_parser = subparsers.add_parser("list", help="List all rate limit blocks")
    
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
    
    elif args.command == "clear-all":
        confirm = input("⚠️  This will clear ALL rate limits. Are you sure? (yes/no): ")
        if confirm.lower() == "yes":
            clear_rate_limit()
        else:
            print("Operation cancelled.")
    
    elif args.command == "status":
        get_status(key=args.key)
    
    elif args.command == "list":
        list_all_blocks()
    
    elif args.command == "my-key":
        get_current_key()


if __name__ == "__main__":
    main()