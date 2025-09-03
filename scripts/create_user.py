# scripts/create_user.py
import sys
import getpass
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError
from models import engine, User
from auth.security import hash_password

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

MIN_LEN = 8

def prompt_password() -> str:
    """
    Prompt for a password twice, require a minimal length, and match.
    """
    while True:
        pw1 = getpass.getpass("New password: ")
        if len(pw1) < MIN_LEN:
            print(f"Password must be at least {MIN_LEN} characters.", file=sys.stderr)
            continue
        pw2 = getpass.getpass("Confirm password: ")
        if pw1 != pw2:
            print("Passwords do not match. Try again.", file=sys.stderr)
            continue
        return pw1

def main() -> None:
    try:
        username = input("Username: ").strip()
        if not username:
            print("Username cannot be empty.", file=sys.stderr)
            sys.exit(1)

        with SessionLocal() as db:
            # Case-insensitive exact match
            user = db.query(User).filter(User.username.ilike(username)).first()

            if user:
                print(f"User '{user.username}' exists.")
                choice = input("Reset password? [y/N]: ").strip().lower()
                if choice != "y":
                    print("No changes made.")
                    return

                new_pw = prompt_password()
                user.password_hash = hash_password(new_pw)
                db.add(user)
                db.commit()
                print(f"Password reset for user '{user.username}'.")
                return

            # Create new user
            password = prompt_password()
            u = User(username=username, password_hash=hash_password(password))
            db.add(u)
            db.commit()
            print(f"User '{u.username}' created.")

    except KeyboardInterrupt:
        print("\nAborted by user.", file=sys.stderr)
        sys.exit(1)
    except SQLAlchemyError as e:
        print(f"Database error: {e}", file=sys.stderr)
        sys.exit(2)

if __name__ == "__main__":
    main()
