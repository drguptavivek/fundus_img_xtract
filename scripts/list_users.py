#!/usr/bin/env python3
# scripts/list_users.py
import sys
from pathlib import Path
import os
import argparse
import pytz

from utils.env_loader import load_environment
load_environment()

# Add the project root to the path so we can import models
# This approach is more robust and handles different execution contexts
file_path = Path(__file__).resolve()
project_root = file_path.parent.parent
sys.path.insert(0, str(project_root))

# Now we can import the modules
try:
    from sqlalchemy.exc import SQLAlchemyError
    from models import User
    from db_transaction_manager import get_db_session
except ModuleNotFoundError as e:
    print(f"Error importing modules: {e}", file=sys.stderr)
    print(f"Current working directory: {os.getcwd()}", file=sys.stderr)
    print(f"Project root: {project_root}", file=sys.stderr)
    print(f"Python path: {sys.path[:5]}", file=sys.stderr)  # Show first 5 paths
    sys.exit(1)


def format_datetime(dt):
    """Format datetime for display with timezone handling."""
    if dt is None:
        return "Never"

    # Convert to IST for display
    ist_tz = pytz.timezone('Asia/Kolkata')
    if dt.tzinfo is None:
        dt = pytz.utc.localize(dt)
    local_dt = dt.astimezone(ist_tz)

    return local_dt.strftime("%Y-%m-%d %H:%M:%S IST")


def list_users(verbose=False, show_inactive=False):
    """
    List all users with their details.

    Args:
        verbose (bool): Show detailed information
        show_inactive (bool): Include inactive users
    """
    try:
        with get_db_session() as db:
            query = db.query(User)

            if not show_inactive:
                query = query.filter(User.is_active == True)

            users = query.order_by(User.username).all()

            if not users:
                print("No users found.")
                return

            print(f"\n{'='*80}")
            print(f"{'USERS LIST':^80}")
            print(f"{'='*80}")
            print(f"{'Username':<20} {'Email':<25} {'Roles':<20} {'Created':<15}")
            print(f"{'-'*80}")

            for user in users:
                roles_str = ", ".join([role.name for role in user.roles]) if user.roles else "None"
                created_str = format_datetime(user.created_at)

                print(f"{user.username:<20} {user.email or 'N/A':<25} {roles_str:<20} {created_str:<15}")

                if verbose:
                    print(f"  ID: {user.id}")
                    print(f"  Full Name: {user.full_name or 'Not set'}")
                    print(f"  Phone: {user.phone or 'Not set'}")
                    print(f"  Email: {user.email or 'Not set'}")
                    print(f"  Designation: {user.designation or 'Not set'}")
                    print(f"  Timezone: {user.timezone or 'Not set'}")
                    print(f"  Created: {format_datetime(user.created_at)}")
                    print(f"  Updated: {format_datetime(user.updated_at)}")
                    print(f"  Active: {user.is_active}")
                    print(f"  File Upload Quota: {user.file_upload_quota}")
                    print(f"  File Upload Count: {user.file_upload_count}")
                    if user.last_date_of_service:
                        print(f"  Last Date of Service: {user.last_date_of_service}")
                    if user.year_of_joining:
                        print(f"  Year of Joining: {user.year_of_joining}")
                    print()

            print(f"\nTotal users: {len(users)}")

    except SQLAlchemyError as e:
        print(f"Database error: {e}", file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(3)


def main() -> None:
    parser = argparse.ArgumentParser(description="List all users in the system")
    parser.add_argument("-v", "--verbose", action="store_true",
                       help="Show detailed user information")
    parser.add_argument("-a", "--all", action="store_true",
                       help="Include inactive users")

    args = parser.parse_args()

    try:
        list_users(verbose=args.verbose, show_inactive=args.all)
    except KeyboardInterrupt:
        print("\nAborted by user.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()