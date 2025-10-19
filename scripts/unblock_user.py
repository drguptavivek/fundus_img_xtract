#!/usr/bin/env python3
"""
Script to unblock a locked IP address or user account.
Run this script to remove IP locks and user account locks.
"""

import sys
import os
from datetime import datetime, timezone

# Add the parent directory to the path so we can import our modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, delete
from models import engine, Session, User, IpLock, LoginAttempt
from auth.utils import get_client_ip

def unblock_ip(ip_address=None):
    """Remove IP lock for a specific IP or all IPs."""
    with Session() as db:
        if ip_address:
            # Remove lock for specific IP
            result = db.execute(delete(IpLock).where(IpLock.ip_address == ip_address))
            db.commit()
            if result.rowcount > 0:
                print(f"✓ Unblocked IP: {ip_address}")
            else:
                print(f"✗ No lock found for IP: {ip_address}")
        else:
            # Remove all IP locks
            result = db.execute(delete(IpLock))
            db.commit()
            print(f"✓ Removed {result.rowcount} IP locks")

def unblock_user(username=None):
    """Remove user account lock for a specific user or all users."""
    with Session() as db:
        if username:
            # Find user
            user = db.execute(select(User).where(func.lower(User.username) == func.lower(username))).scalar_one_or_none()
            if user:
                if user.is_locked_until:
                    user.is_locked_until = None
                    db.add(user)
                    db.commit()
                    print(f"✓ Unlocked user: {username}")
                else:
                    print(f"✗ User {username} is not locked")
            else:
                print(f"✗ User not found: {username}")
        else:
            # Unlock all users
            users = db.execute(select(User).where(User.is_locked_until.isnot(None))).scalars().all()
            count = 0
            for user in users:
                user.is_locked_until = None
                db.add(user)
                count += 1
            db.commit()
            print(f"✓ Unlocked {count} users")

def clear_login_attempts(ip_address=None, username=None):
    """Clear login attempts for an IP or username."""
    with Session() as db:
        if ip_address:
            result = db.execute(delete(LoginAttempt).where(LoginAttempt.ip_address == ip_address))
            db.commit()
            print(f"✓ Cleared {result.rowcount} login attempts for IP: {ip_address}")
        
        if username:
            result = db.execute(delete(LoginAttempt).where(func.lower(LoginAttempt.username_input) == func.lower(username)))
            db.commit()
            print(f"✓ Cleared {result.rowcount} login attempts for username: {username}")

def show_status():
    """Show current lock status."""
    print("\n=== Current Lock Status ===")
    
    with Session() as db:
        # Show IP locks
        ip_locks = db.execute(select(IpLock)).scalars().all()
        if ip_locks:
            print("\nIP Locks:")
            for lock in ip_locks:
                formatted_time = lock.locked_until.strftime("%Y-%m-%d %H:%M:%S %Z")
                print(f"  - {lock.ip_address} (locked until {formatted_time})")
        else:
            print("\nNo IP locks found")
        
        # Show user locks
        user_locks = db.execute(select(User).where(User.is_locked_until.isnot(None))).scalars().all()
        if user_locks:
            print("\nUser Locks:")
            for user in user_locks:
                formatted_time = user.is_locked_until.strftime("%Y-%m-%d %H:%M:%S %Z")
                print(f"  - {user.username} (locked until {formatted_time})")
        else:
            print("\nNo user locks found")

def main():
    """Main function to handle command line arguments."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Unblock IP addresses and user accounts")
    parser.add_argument("--ip", help="Unblock specific IP address")
    parser.add_argument("--all-ips", action="store_true", help="Unblock all IP addresses")
    parser.add_argument("--user", help="Unblock specific username")
    parser.add_argument("--all-users", action="store_true", help="Unblock all users")
    parser.add_argument("--clear-attempts-ip", help="Clear login attempts for IP")
    parser.add_argument("--clear-attempts-user", help="Clear login attempts for username")
    parser.add_argument("--status", action="store_true", help="Show current lock status")
    parser.add_argument("--unblock-all", action="store_true", help="Unblock everything (IPs, users, and clear attempts)")
    
    args = parser.parse_args()
    
    if args.status:
        show_status()
        return
    
    if args.unblock_all:
        print("Unblocking all IPs and users...")
        unblock_ip()
        unblock_user()
        print("\n✓ All IPs and users have been unlocked")
        return
    
    if args.all_ips:
        unblock_ip()
    
    if args.ip:
        unblock_ip(args.ip)
    
    if args.all_users:
        unblock_user()
    
    if args.user:
        unblock_user(args.user)
    
    if args.clear_attempts_ip:
        clear_login_attempts(ip_address=args.clear_attempts_ip)
    
    if args.clear_attempts_user:
        clear_login_attempts(username=args.clear_attempts_user)
    
    if not any([args.ip, args.all_ips, args.user, args.all_users, 
                args.clear_attempts_ip, args.clear_attempts_user, 
                args.status, args.unblock_all]):
        print("No action specified. Use --help for options.")
        print("\nQuick unblock options:")
        print("  --unblock-all                    Unblock everything")
        print("  --status                         Show current lock status")
        print("  --ip <IP_ADDRESS>               Unblock specific IP")
        print("  --user <USERNAME>                Unblock specific user")

if __name__ == "__main__":
    # Import func here to avoid circular imports
    from sqlalchemy import func
    
    main()