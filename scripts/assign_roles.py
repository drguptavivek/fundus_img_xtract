# scripts/assign_roles.py
import argparse
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from models import engine, User, Role
from auth.roles import ensure_roles, DEFAULT_ROLES

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("username")
    p.add_argument("--roles", nargs="+", default=["fileUploader"])
    args = p.parse_args()

    with SessionLocal() as db:
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
