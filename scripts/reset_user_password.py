#!/usr/bin/env python3
# scripts/reset_user_password.py
import sys
import getpass
from pathlib import Path
import os
import argparse

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
    from auth.security import hash_password
    from db_transaction_manager import get_db_session
except ModuleNotFoundError as e:
    print(f"Error importing modules: {e}", file=sys.stderr)
    print(f"Current working directory: {os.getcwd()}", file=sys.stderr)
    print(f"Project root: {project_root}", file=sys.stderr)
    print(f"Python path: {sys.path[:5]}", file=sys.stderr)  # Show first 5 paths
    sys.exit(1)

MIN_LEN = 8


def prompt_password() -> str:
    """
    Prompt for a password twice, require a minimal length, and match.
    """
    while True:
        try:
            pw1 = getpass.getpass("New password: ")
            if len(pw1) < MIN_LEN:
                print(f"Password must be at least {MIN_LEN} characters.", file=sys.stderr)
                continue
            pw2 = getpass.getpass("Confirm password: ")
            if pw1 != pw2:
                print("Passwords do not match. Try again.", file=sys.stderr)
                continue
            return pw1
        except EOFError:
            print("\nInput cancelled.", file=sys.stderr)
            sys.exit(1)
        except KeyboardInterrupt:
            print("\nOperation cancelled by user.", file=sys.stderr)
            sys.exit(1)


def reset_user_password(username, password=None, force=False):
    """
    Reset password for an existing user.

    Args:
        username (str): Username of the user
        password (str, optional): New password (if not provided, will prompt)
        force (bool): Skip confirmation prompt
    """
    if not username:
        print("Username cannot be empty.", file=sys.stderr)
        sys.exit(1)

    with get_db_session() as db:
        # Case-insensitive exact match
        user = db.query(User).filter(User.username.ilike(username)).first()

        if not user:
            print(f"User '{username}' not found.", file=sys.stderr)
            sys.exit(1)

        # User found - proceed with password reset
        print(f"User '{user.username}' found (ID: {user.id})")
        print(f"Email: {user.email or 'Not set'}")
        print(f"Full Name: {user.full_name or 'Not set'}")
        print(f"Designation: {user.designation or 'Not set'}")
        print(f"Roles: {', '.join([role.name for role in user.roles]) if user.roles else 'None'}")
        print(f"Active: {user.is_active}")
        print(f"Created: {user.created_at.strftime('%Y-%m-%d %H:%M:%S') if user.created_at else 'Unknown'}")
        if user.last_date_of_service:
            print(f"Last Date of Service: {user.last_date_of_service}")
        if user.year_of_joining:
            print(f"Year of Joining: {user.year_of_joining}")

        if not force and password is None:
            # Interactive mode - ask for confirmation
            try:
                choice = input("\nReset password for this user? [y/N]: ").strip().lower()
                if choice != "y":
                    print("Password reset cancelled.")
                    return
            except EOFError:
                print("\nInput cancelled.", file=sys.stderr)
                sys.exit(1)
            except KeyboardInterrupt:
                print("\nOperation cancelled by user.", file=sys.stderr)
                sys.exit(1)

        # Get the new password
        if password is None:
            password = prompt_password()
        else:
            # Non-interactive mode, validate provided password
            if len(password) < MIN_LEN:
                print(f"Password must be at least {MIN_LEN} characters.", file=sys.stderr)
                sys.exit(1)

        # Update the password
        user.password_hash = hash_password(password)
        db.add(user)
        db.commit()

        print(f"\nPassword successfully reset for user '{user.username}'.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset password for an existing user")
    parser.add_argument("username", help="Username of the user")
    parser.add_argument("-p", "--password", help="New password (if not provided, will prompt)")
    parser.add_argument("-f", "--force", action="store_true",
                       help="Skip confirmation prompt")

    args = parser.parse_args()

    try:
        reset_user_password(args.username, args.password, args.force)
    except KeyboardInterrupt:
        print("\nAborted by user.", file=sys.stderr)
        sys.exit(1)
    except SQLAlchemyError as e:
        print(f"Database error: {e}", file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(3)


if __name__ == "__main__":
    main()