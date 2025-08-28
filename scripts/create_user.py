# scripts/create_user.py
import getpass
from sqlalchemy.orm import sessionmaker
from models import engine, User  # uses the new User model
from auth.security import hash_password

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

def main():
    username = input("Username: ").strip()
    password = getpass.getpass("Password: ")
    with SessionLocal() as db:
        if db.query(User).filter(User.username.ilike(username)).first():
            print("User exists.")
            return
        u = User(username=username, password_hash=hash_password(password))
        db.add(u)
        db.commit()
        print("User created.")

if __name__ == "__main__":
    main()
