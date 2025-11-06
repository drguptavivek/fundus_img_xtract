# scripts/assign_roles.py
from pathlib import Path
import os
import argparse
import sys

# Add the project root to the path so we can import models
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
    
    import argparse
from sqlalchemy import select
from models import User, Role
from auth.roles import ensure_roles, DEFAULT_ROLES
from db_transaction_manager import get_db_session

def main():
    p = argparse.ArgumentParser()
    p.add_argument("username")
    p.add_argument("--roles", nargs="+", default=["fileUploader"])
    args = p.parse_args()

    with get_db_session() as db:
        ensure_roles(db, DEFAULT_ROLES)
        user = db.execute(select(User).where(User.username.ilike(args.username))).scalar_one_or_none()
        if not user:
            print("No such user.")
            return
        # attach roles
        roles = db.scalars(select(Role).where(Role.name.in_(args.roles))).all()
        existing = {r.name for r in (user.roles or [])}
        for r in roles:
            if r.name not in existing:
                user.roles.append(r)
        db.add(user)
        db.commit()
        print(f"User '{user.username}' now has roles: {[r.name for r in user.roles]}")

if __name__ == "__main__":
    main()
