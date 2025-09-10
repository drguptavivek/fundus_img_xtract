# scripts/test_db.py
import sys
from pathlib import Path

# Add the project root to the path so we can import models
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models import engine, User
from sqlalchemy.orm import sessionmaker

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

def main():
    print("Testing database connection...")
    try:
        with SessionLocal() as db:
            # Try a simple query
            count = db.query(User).count()
            print(f"Database connection successful. Found {count} users in the database.")
    except Exception as e:
        print(f"Database connection failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()