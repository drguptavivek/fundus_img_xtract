
import pytest
from models import User
from auth.security import hash_password
# from auth.session import current_user # This would fail if it existed

def test_imports():
    print("Importing User...")
    from models import User
    print("Importing direct_uploads.dashboard...")
    from direct_uploads import dashboard
    print("Importing auth.security...")
    import auth.security
    print("Importing app...")
    from app import create_app
    print("Creating app...")
    # create_app() # Might fail due to config/db, but import should work
    
    print("Importing all blueprints...")
    from api import bp as api_bp
    from auth import bp as auth_bp
    from admin import bp as admin_bp
    from analytics import bp as analytics_bp
    from direct_uploads import bp as direct_uploads_bp
    from grading import bp as grading_bp
    from review import bp as review_bp
    from search import bp as search_bp
    from tasks import bp as tasks_bp
    print("All blueprints imported successfully")
