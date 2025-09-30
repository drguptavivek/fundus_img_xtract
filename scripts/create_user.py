#!/usr/bin/env python3
# scripts/create_user.py
import sys
import getpass
from pathlib import Path
import os
import argparse

# Add the project root to the path so we can import models
# This approach is more robust and handles different execution contexts
file_path = Path(__file__).resolve()
project_root = file_path.parent.parent
sys.path.insert(0, str(project_root))

# Now we can import the modules
try:
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.exc import SQLAlchemyError
    from models import engine, User
    from auth.security import hash_password
    from utils.timezone_choices import DEFAULT_TIMEZONE
except ModuleNotFoundError as e:
    print(f"Error importing modules: {e}", file=sys.stderr)
    print(f"Current working directory: {os.getcwd()}", file=sys.stderr)
    print(f"Project root: {project_root}", file=sys.stderr)
    print(f"Python path: {sys.path[:5]}", file=sys.stderr)  # Show first 5 paths
    sys.exit(1)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

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


def create_user(username, password=None):
    """
    Create a new user or reset password for existing user.
    """
    if not username:
        print("Username cannot be empty.", file=sys.stderr)
        sys.exit(1)

    with SessionLocal() as db:
        # Case-insensitive exact match
        user = db.query(User).filter(User.username.ilike(username)).first()

        if user:
            print(f"User '{user.username}' exists.")
            if password is None:
                # Interactive mode
                try:
                    choice = input("Reset password? [y/N]: ").strip().lower()
                except EOFError:
                    print("\nInput cancelled.", file=sys.stderr)
                    sys.exit(1)
                except KeyboardInterrupt:
                    print("\nOperation cancelled by user.", file=sys.stderr)
                    sys.exit(1)
                    
                if choice != "y":
                    print("No changes made.")
                    return
                password = prompt_password()
            else:
                # Non-interactive mode, use provided password
                if len(password) < MIN_LEN:
                    print(f"Password must be at least {MIN_LEN} characters.", file=sys.stderr)
                    sys.exit(1)

            user.password_hash = hash_password(password)
            db.add(user)
            db.commit()
            print(f"Password reset for user '{user.username}'.")
            return


        # Create new user
        if password is None:
            # Interactive mode
            password = prompt_password()
        else:
            # Non-interactive mode, use provided password
            if len(password) < MIN_LEN:
                print(f"Password must be at least {MIN_LEN} characters.", file=sys.stderr)
                sys.exit(1)
                
        u = User(
            username=username,
            password_hash=hash_password(password),
            timezone=os.getenv("DEFAULT_DISPLAY_TIMEZONE", DEFAULT_TIMEZONE),
        )
        db.add(u)
        db.commit()
        print(f"User '{u.username}' created.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a new user or reset password for existing user")
    parser.add_argument("username", help="Username")
    parser.add_argument("-p", "--password", help="Password (if not provided, will prompt)")
    
    args = parser.parse_args()
    
    try:
        create_user(args.username, args.password)
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
